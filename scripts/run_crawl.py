import argparse
import json
import logging
from pathlib import Path

from event_agent.config import settings
from event_agent.graph.builder import build_graph
from event_agent.utils.logging import setup_logging

log = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl a paginated listing site and extract structured records.")
    parser.add_argument("--base-url", required=True, help='URL шаблон, напр. "https://qr-pib.kz/ru/post/?page={n}"')
    parser.add_argument("--max-pages", type=int, default=settings.max_pages)
    parser.add_argument("--output", default="output/events.json")
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_args()

    app = build_graph()
    result = app.invoke(
        {
            "base_list_url": args.base_url,
            "current_page": 1,
            "max_pages": args.max_pages,
            "event_urls": [],
            "all_records": [],
            "stop": False,
        },
        config={"recursion_limit": (args.max_pages + 1) * 3},
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = [r.model_dump() for r in result["all_records"]]
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("Saved %d records to %s", len(records), out_path)


if __name__ == "__main__":
    main()
