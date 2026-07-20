from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_daily",
    ROOT / "scripts" / "publish_daily.py",
)
assert SPEC and SPEC.loader
publish_daily = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish_daily
SPEC.loader.exec_module(publish_daily)


class PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ideas = publish_daily.load_ideas()
        self.idea = self.ideas[0]
        self.payload = publish_daily.render_fixture(self.idea)

    def test_selects_first_idea_on_launch_date(self) -> None:
        selected = publish_daily.select_idea(
            date(2026, 7, 20),
            date(2026, 7, 20),
            self.ideas,
        )
        self.assertEqual(selected.slug, "twincat-traffic-light")

    def test_idea_queue_wraps(self) -> None:
        selected = publish_daily.select_idea(
            date(2026, 7, 20),
            date(2026, 7, 20),
            self.ideas,
        )
        wrapped = publish_daily.select_idea(
            date.fromordinal(date(2026, 7, 20).toordinal() + len(self.ideas)),
            date(2026, 7, 20),
            self.ideas,
        )
        self.assertEqual(selected.slug, wrapped.slug)

    def test_fixture_passes_validation(self) -> None:
        project = publish_daily.validate_project(self.payload, self.idea.slug)
        paths = {item.path for item in project.files}
        self.assertTrue(publish_daily.REQUIRED_FILES <= paths)

    def test_rejects_path_traversal(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["files"][0]["path"] = "../README.md"
        with self.assertRaisesRegex(publish_daily.PublisherError, "Unsafe project path"):
            publish_daily.validate_project(payload, self.idea.slug)

    def test_rejects_dangerous_python_call(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["files"][3]["content"] = "eval('2 + 2')\n"
        with self.assertRaisesRegex(publish_daily.PublisherError, "Blocked call"):
            publish_daily.validate_project(payload, self.idea.slug)

    def test_rejects_direct_plc_io_mapping(self) -> None:
        payload = copy.deepcopy(self.payload)
        plc_file = next(item for item in payload["files"] if item["path"] == "plc/MAIN.st")
        plc_file["content"] = (
            "PROGRAM MAIN\nVAR\nbInput AT %IX0.0 : BOOL;\nEND_VAR\nEND_PROGRAM\n"
        )
        with self.assertRaisesRegex(publish_daily.PublisherError, "direct hardware"):
            publish_daily.validate_project(payload, self.idea.slug)

    def test_extracts_responses_api_output_text(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
                }
            ]
        }
        self.assertEqual(publish_daily.extract_output_text(response), "{\"ok\": true}")

    def test_profile_update_keeps_only_limit(self) -> None:
        readme = (
            "# Profile\n\n"
            f"{publish_daily.PROFILE_START}\n"
            "- [Old One](https://example.com/1) — first\n"
            "- [Old Two](https://example.com/2) — second\n"
            f"{publish_daily.PROFILE_END}\n"
        )
        updated = publish_daily.update_profile_block(
            readme,
            title="New",
            description="A new automation",
            url="https://example.com/new",
            limit=2,
        )
        self.assertIn("[New](https://example.com/new)", updated)
        self.assertIn("[Old One](https://example.com/1)", updated)
        self.assertNotIn("[Old Two](https://example.com/2)", updated)

    def test_profile_update_is_idempotent_for_same_url(self) -> None:
        readme = (
            f"{publish_daily.PROFILE_START}\n"
            "- [Existing](https://example.com/same) — old description\n"
            f"{publish_daily.PROFILE_END}\n"
        )
        updated = publish_daily.update_profile_block(
            readme,
            title="Existing",
            description="new description",
            url="https://example.com/same",
            limit=6,
        )
        self.assertEqual(updated.count("https://example.com/same"), 1)
        self.assertIn("new description", updated)


if __name__ == "__main__":
    unittest.main()
