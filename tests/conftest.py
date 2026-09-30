import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# тесты должны быть оффлайн и не писать в репозиторий
os.environ.setdefault("SINTGAME_CACHE", tempfile.mkdtemp(prefix="sintgame-test-"))
os.environ.setdefault("SINT_GEN_CMD", "none")  # LLM недоступен -> штатная деградация
