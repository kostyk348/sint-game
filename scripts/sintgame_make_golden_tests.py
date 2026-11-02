#!/usr/bin/env python3
"""Convert scripts/sintgame_golden.json into a Rust test-data file."""
import json
import os


def rust_str(s):
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{{{ord(ch):x}}}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def main():
    data = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sintgame_golden.json")))
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    worlds = {}
    for name in ("campaign", "sandbox", "station", "lighthouse"):
        with open(f"{REPO}/examples/{name}/world.json", encoding="utf-8") as f:
            worlds[name] = f.read()

    lines = [
        "// Golden cases generated from the ORIGINAL Python implementation",
        "// (scripts/sintgame_golden.py + scripts/sintgame_golden.json).",
        "// Regenerate: python3 scripts/sintgame_make_golden_tests.py",
        "",
        "pub struct WorldCase {",
        "    pub name: &'static str,",
        "    pub world: &'static str,",
        "    pub seed: i64,",
        "    pub steps: usize,",
        "    pub save_at: usize,",
        "    pub validate_errors: &'static [&'static str],",
        "    pub simulate: &'static str,",
        "    pub trace: &'static str,",
        "    pub final_state: &'static str,",
        "    pub restored_state: &'static str,",
        "}",
        "",
        "pub const WORLDS: &[WorldCase] = &[",
    ]
    play_keys = {k for k in data if k.endswith(":play")}
    for name, world_src in worlds.items():
        k = f"{name}:play"
        play = json.loads(data[k])
        val = data[f"{name}:validate"]["errors"]
        errs = ", ".join(rust_str(e) for e in val)
        lines.append("    WorldCase {")
        lines.append(f"        name: {rust_str(name)},")
        lines.append(f"        world: {rust_str(world_src)},")
        lines.append(f"        seed: 7,")
        lines.append(f"        steps: 25,")
        lines.append(f"        save_at: 10,")
        lines.append(f"        validate_errors: &[{errs}],")
        lines.append(f"        simulate: {rust_str(data[f'{name}:simulate'])},")
        lines.append(f"        trace: {rust_str(data[k])},")
        lines.append(f"        final_state: {rust_str(play['final_state'])},")
        lines.append(f"        restored_state: {rust_str(play['restored_state'])},")
        lines.append("    },")
    lines.append("];")
    lines.append("")

    # IR compile + link cases
    rich_spec = open("/home/z/my-project/scripts/sintgame_rich_spec.json", encoding="utf-8").read() \
        if False else None
    lines.append("pub struct IrCase {")
    lines.append("    pub name: &'static str,")
    lines.append("    pub spec: &'static str,")
    lines.append("    pub compile: Option<&'static str>,")
    lines.append("    pub link_errors: &'static [&'static str],")
    lines.append("}")
    lines.append("")
    lines.append("pub const IR_CASES: &[IrCase] = &[")

    # rich spec embedded verbatim (extract from the golden script source)
    import importlib.util
    spec_mod = importlib.util.spec_from_file_location(
        "sg", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sintgame_golden.py"))
    # we can't import (it runs main); parse RICH_SPEC via exec of the dict literal
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sintgame_golden.py"), encoding="utf-8").read()
    ns = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "sintgame_golden.py")}
    exec(compile(src.split("def canonical(")[0], "frag", "exec"), ns)
    rich = ns["RICH_SPEC"]
    broken = ns["BROKEN_SPEC"]
    rich_link = data["rich:link"]["errors"]
    link_errs_rich = ", ".join(rust_str(e) for e in rich_link)
    lines.append("    IrCase {")
    lines.append(f"        name: \"rich\",")
    lines.append(f"        spec: {rust_str(json.dumps(rich, ensure_ascii=False, sort_keys=True))},")
    lines.append(f"        compile: Some({rust_str(data['rich:compile'])}),")
    lines.append(f"        link_errors: &[{link_errs_rich}],")
    lines.append("    },")
    lines.append("    IrCase {")
    lines.append(f"        name: \"broken\",")
    lines.append(f"        spec: {rust_str(json.dumps(broken, ensure_ascii=False, sort_keys=True))},")
    lines.append(f"        compile: None,")
    link_errs = data["broken:link"]["errors"]
    lines.append(f"        link_errors: &[{', '.join(rust_str(e) for e in link_errs)}],")
    lines.append("    },")
    lines.append("];")
    lines.append("")

    # rich flat world + play
    lines.append("pub const RICH_FLAT_WORLD: &str =")
    lines.append(f"    {rust_str(data['rich:compile'])};")
    lines.append("")
    lines.append("pub const RICH_PLAY: &str =")
    lines.append(f"    {rust_str(data['rich:play'])};")
    lines.append("")


    open(os.path.join(REPO, "tests", "golden_cases.rs"), "w").write(
        "\n".join(lines))
    print("wrote tests/golden_cases.rs")


if __name__ == "__main__":
    main()
