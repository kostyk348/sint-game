.PHONY: test validate demo compile clean install

test:
	python3 -m pytest -q

validate:
	python3 -m sintgame validate examples/lighthouse/world.json
	python3 -m sintgame validate examples/station/world.json

demo:
	python3 -m sintgame play examples/lighthouse/world.json \
		--script talk_iya,press_marek,search_cabin,reveal_truth --prose none

compile:
	python3 -m sintgame compile examples/lighthouse/lore.md -o /tmp/world.json

install:
	pip install -e .

clean:
	rm -rf .sintgame .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.ext.json' -delete
