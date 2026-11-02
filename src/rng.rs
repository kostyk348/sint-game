//! CPython-совместимый MT19937 (`random.Random`).
//!
//! Бит-в-бит повторяет `_randommodule.c`: seeding через `init_by_array`
//! (модуль seed → 32-битные слова LE), `getrandbits` со словом-старшим
//! справа, `_randbelow` c повторными бросками, `randint(a, b)`.
//! Благодаря этому сейвы и прогоны Python-прототипа воспроизводятся в Rust
//! один в один (контракт «воспроизводимые сейвы» сохраняется).
//!
//! `gauss`-кэш хранится в состоянии (None), но не используется: `World.roll`
//! задействует только `randint`.

const N: usize = 624;
const MATRIX_A: u32 = 0x9908_B0DF;
const UPPER_MASK: u32 = 0x8000_0000;
const LOWER_MASK: u32 = 0x7FFF_FFFF;

#[derive(Clone)]
pub struct PyRandom {
    mt: [u32; N],
    index: usize,
    gauss_next: Option<f64>,
}

impl std::fmt::Debug for PyRandom {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PyRandom")
            .field("index", &self.index)
            .field("gauss_next", &self.gauss_next)
            .finish()
    }
}

impl PyRandom {
    /// random.Random(seed) — seed_i64 берётся по модулю 2^32 как в CPython
    /// (`PyNumber_Absolute` → 32-битные слова LE; отрицательные дают слова
    /// модуля, знак теряется).
    pub fn new(seed: i64) -> PyRandom {
        let mut r = PyRandom {
            mt: [0; N],
            index: N,
            gauss_next: None,
        };
        // |seed| -> 32-битные слова LE; 0 -> одно слово 0 (keyused = bits==0 ? 1 : ...)
        let mag = (seed as i128).unsigned_abs();
        let mut key: Vec<u32> = Vec::new();
        if mag == 0 {
            key.push(0);
        } else {
            let mut m = mag;
            while m > 0 {
                key.push((m & 0xFFFF_FFFF) as u32);
                m >>= 32;
            }
        }
        r.init_by_array(&key);
        r
    }

    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            self.mt[i] = 1812433253u32
                .wrapping_mul(self.mt[i - 1] ^ (self.mt[i - 1] >> 30))
                .wrapping_add(i as u32);
        }
        self.index = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19650218);
        let mut i = 1usize;
        let mut j = 0usize;
        let k = N.max(key.len());
        for _ in 0..k {
            self.mt[i] = (self.mt[i]
                ^ ((self.mt[i - 1] ^ (self.mt[i - 1] >> 30)).wrapping_mul(1664525)))
            .wrapping_add(key[j])
            .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..(N - 1) {
            self.mt[i] = (self.mt[i]
                ^ ((self.mt[i - 1] ^ (self.mt[i - 1] >> 30)).wrapping_mul(1566083941)))
            .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
        }
        self.mt[0] = 0x8000_0000;
        self.index = N;
    }

    fn regenerate(&mut self) {
        for i in 0..N {
            let y = (self.mt[i] & UPPER_MASK) | (self.mt[(i + 1) % N] & LOWER_MASK);
            self.mt[i] = self.mt[(i + 397) % N] ^ (y >> 1);
            if y & 1 != 0 {
                self.mt[i] ^= MATRIX_A;
            }
        }
        self.index = 0;
    }

    pub fn genrand_u32(&mut self) -> u32 {
        if self.index >= N {
            self.regenerate();
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9D2C_5680;
        y ^= (y << 15) & 0xEFC6_0000;
        y ^= y >> 18;
        y
    }

    /// random.random(): genrand_res53.
    pub fn random(&mut self) -> f64 {
        let a = (self.genrand_u32() >> 5) as f64;
        let b = (self.genrand_u32() >> 6) as f64;
        (a * 67108864.0 + b) / 9007199254740992.0
    }

    /// random.getrandbits(k).
    pub fn getrandbits(&mut self, k: u32) -> u64 {
        if k == 0 {
            return 0;
        }
        let words = ((k - 1) / 32 + 1) as usize;
        let mut acc: u64 = 0;
        let mut remaining = k;
        for i in 0..words {
            let mut w = self.genrand_u32();
            if remaining < 32 {
                w >>= 32 - remaining;
            }
            acc |= (w as u64) << (32 * i);
            remaining = remaining.saturating_sub(32);
        }
        acc
    }

    /// random._randbelow_with_getrandbits(n): k = n.bit_length(), повтор до < n.
    pub fn randbelow(&mut self, n: u64) -> u64 {
        debug_assert!(n > 0);
        let k = 64 - n.leading_zeros();
        loop {
            let r = self.getrandbits(k);
            if r < n {
                return r;
            }
        }
    }

    /// random.randint(a, b) = a + _randbelow(b - a + 1).
    pub fn randint(&mut self, a: i64, b: i64) -> i64 {
        a + self.randbelow((b - a + 1) as u64) as i64
    }

    /// random.choice по индексу (для выбора действия в simulate).
    pub fn below_for_choice(&mut self, seq_len: usize) -> usize {
        self.randbelow(seq_len as u64) as usize
    }

    /// state() в формате CPython: (version, [mt..624 + index] — 625 элементов,
    /// gauss). Сериализуется в сейвы, совместимые с Python `getstate`/`setstate`.
    pub fn export_state(&self) -> (u64, Vec<u32>, Option<f64>) {
        let mut internal = self.mt.to_vec();
        internal.push(self.index as u32);
        (3, internal, self.gauss_next)
    }

    pub fn import_state(&mut self, version: u64, internal: &[u32], gauss: Option<f64>) {
        assert_eq!(version, 3, "неизвестная версия state random");
        assert_eq!(
            internal.len(),
            N + 1,
            "внутреннее состояние — 624 слова + индекс"
        );
        self.mt.copy_from_slice(&internal[..N]);
        self.index = internal[N] as usize;
        self.gauss_next = gauss;
    }

    /// Внутренний экспорт для тестов: (index, mt, gauss).
    pub fn export_full(&self) -> (usize, [u32; N], Option<f64>) {
        (self.index, self.mt, self.gauss_next)
    }

    pub fn import_full(&mut self, index: usize, mt: [u32; N], gauss: Option<f64>) {
        self.index = index;
        self.mt = mt;
        self.gauss_next = gauss;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Золотые значения из CPython 3.12 (scripts/sintgame_golden.py):
    #[test]
    fn randint_matches_cpython() {
        let mut r = PyRandom::new(42);
        let got: Vec<i64> = (0..5).map(|_| r.randint(1, 6)).collect();
        assert_eq!(got, [6, 1, 1, 6, 3], "Random(42).randint(1,6) x5");
        assert_eq!(PyRandom::new(0).randint(0, 1_000_000), 885_440);
        assert_eq!(PyRandom::new(i64::MAX).randint(0, 1_000_000), 332_026);
    }

    #[test]
    fn zero_and_large_seeds() {
        let mut r = PyRandom::new(0);
        let a = r.randint(0, 1_000_000);
        let mut r = PyRandom::new(i64::MAX);
        let b = r.randint(0, 1_000_000);
        // значения сверяются golden-тестом против Python; тут только детерминизм
        let mut r2 = PyRandom::new(0);
        assert_eq!(r2.randint(0, 1_000_000), a);
        let mut r2 = PyRandom::new(i64::MAX);
        assert_eq!(r2.randint(0, 1_000_000), b);
    }

    #[test]
    fn state_roundtrip() {
        let mut r = PyRandom::new(7);
        for _ in 0..100 {
            r.randint(1, 100);
        }
        // Python-совместимый формат: после 100 randint(1,100) индекс = 115,
        // следующий randint(1,1_000_000) = 81391 (скрипт golden'ов)
        let (ver, internal, g) = r.export_state();
        assert_eq!(internal.len(), 625);
        assert_eq!(internal[624], 115, "индекс MT после 100 бросков d100");
        let next_after_save = r.randint(1, 1_000_000);
        assert_eq!(next_after_save, 81391);
        let mut r2 = PyRandom::new(0);
        r2.import_state(ver, &internal, g);
        assert_eq!(r2.randint(1, 1_000_000), next_after_save);
    }
}
