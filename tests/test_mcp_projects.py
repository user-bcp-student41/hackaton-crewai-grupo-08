"""El filtro opcional de proyecto no llama al MCP."""

import unittest
from unittest.mock import patch

import mcp_projects

PROJECTS = [
    {"id": "P1", "title": "backlog-ai-labs"},
    {"id": "P2", "title": "hackaton-test-08"},
    {"id": "P3", "title": "backlog-hackaton-grupo-08"},
]


class ListProjectsTests(unittest.TestCase):
    def titles(self, env):
        with patch.dict("os.environ", env), patch.object(mcp_projects, "call_tool", return_value=PROJECTS):
            return [p["title"] for p in mcp_projects.list_projects()]

    def test_empty_filter_defaults_to_the_team_backlog(self):
        self.assertEqual(self.titles({"GITHUB_PROJECT_TITLE": ""}), ["backlog-hackaton-grupo-08"])

    def test_filter_keeps_only_the_exact_title(self):
        self.assertEqual(self.titles({"GITHUB_PROJECT_TITLE": "hackaton-test-08"}), ["hackaton-test-08"])
        self.assertEqual(self.titles({"GITHUB_PROJECT_TITLE": "hackaton"}), [])


class ProjectFeatureTests(unittest.TestCase):
    def test_project_items_follow_mcp_cursors_until_the_batch_is_complete(self):
        pages = [
            {
                "structuredContent": {"items": [{"id": "A", "title": "HU-A"}],
                                     "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}},
                "totalCount": 2,
            },
            {
                "structuredContent": {"items": [{"id": "B", "title": "HU-B"}],
                                     "pageInfo": {"hasNextPage": False}},
                "totalCount": 2,
            },
        ]
        with patch.object(mcp_projects, "call_tool", side_effect=pages) as call:
            items = mcp_projects.list_project_items("P1", limit=1)
        self.assertEqual([item["title"] for item in items], ["HU-A", "HU-B"])
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[1].args[1]["after"], "cursor-1")

    def test_project_items_reject_truncated_results_without_a_cursor(self):
        response = {"items": [{"id": "A", "title": "HU-A"}], "totalCount": 2}
        with patch.object(mcp_projects, "call_tool", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "no expuso cursor"):
                mcp_projects.list_project_items("P1", limit=1)

    def test_feature_list_filters_labels_and_preserves_issue_metadata(self):
        items = [
            {"type": "Issue", "contentId": "I_1", "number": 1, "labels": ["historia"]},
            {"type": "Issue", "contentId": "I_2", "number": 2, "labels": ["bug"]},
        ]

        def feature_for(item):
            return {
                "title": f"HU-{item['number']}", "description": "body",
                "acceptance_criteria": [], "labels": [],
            }

        with patch.object(mcp_projects, "list_project_items", return_value=items), \
                patch.object(mcp_projects, "get_feature_from_item", side_effect=feature_for):
            features = mcp_projects.list_project_features("P1", required_label="Historia")

        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["issue_number"], 1)
        self.assertEqual(features[0]["labels"], ["historia"])

    def test_comments_use_verified_mcp_actions_and_arguments(self):
        with patch.object(mcp_projects, "call_tool", return_value={"comments": [{"body": "Decisión"}]}) as call:
            comments = mcp_projects.list_issue_comments(8)
        self.assertEqual(comments[0]["body"], "Decisión")
        self.assertEqual(call.call_args.args[0], "manage_issues")
        self.assertEqual(call.call_args.args[1]["action"], "list_comments")
        self.assertEqual(call.call_args.args[1]["issueNumber"], 8)

        with patch.object(mcp_projects, "call_tool", return_value={}) as call:
            mcp_projects.create_issue_comment(8, "Análisis aprobado")
        self.assertEqual(call.call_args.args[1]["action"], "create_comment")
        self.assertEqual(call.call_args.args[1]["body"], "Análisis aprobado")


class PublishBacklogTests(unittest.TestCase):
    def test_only_missing_labels_are_created(self):
        calls = []

        def fake(tool, params):
            calls.append((tool, params))
            return [{"name": "Historia"}] if params["action"] == "list" else {}

        with patch.object(mcp_projects, "call_tool", side_effect=fake):
            created = mcp_projects.ensure_labels(["historia", "extension"], {"extension": "Opcional"})
        self.assertEqual(created, ["extension"])
        creates = [p for t, p in calls if t == "manage_labels" and p["action"] == "create"]
        self.assertEqual(creates, [{"action": "create", "name": "extension", "description": "Opcional"}])

    def test_create_issue_returns_node_id_number_and_url(self):
        response = {"id": "I_abc", "number": 9, "labels": ["historia"],
                    "url": mcp_projects.expected_repo_url() + "9"}
        with patch.object(mcp_projects, "call_tool", return_value=response) as call:
            issue = mcp_projects.create_issue("HU-01", "cuerpo", ["historia"])
        self.assertEqual((issue["id"], issue["number"]), ("I_abc", 9))
        params = call.call_args.args[1]
        self.assertEqual((params["action"], params["title"], params["description"], params["labels"]),
                         ("create", "HU-01", "cuerpo", ["historia"]))

    def test_issue_created_in_another_repo_is_reported(self):
        response = {"id": "I_abc", "number": 9, "url": "https://github.com/otro/repo/issues/9"}
        with patch.object(mcp_projects, "call_tool", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "no en"):
                mcp_projects.create_issue("HU-01", "cuerpo", [])

    def test_unexpected_create_response_is_an_error(self):
        with patch.object(mcp_projects, "call_tool", return_value={"raw": "ok"}):
            with self.assertRaisesRegex(RuntimeError, "inesperada"):
                mcp_projects.create_issue("HU-01", "cuerpo", [])

    def test_issue_is_added_to_the_project_by_node_id(self):
        with patch.object(mcp_projects, "call_tool", return_value={}) as call:
            mcp_projects.add_issue_to_project("PVT_1", "I_abc")
        self.assertEqual(call.call_args.args, ("manage_project", {
            "action": "add_item", "projectId": "PVT_1", "contentId": "I_abc", "contentType": "issue"}))

    def test_find_by_marker_matches_the_body_in_open_and_closed_issues(self):
        issues = [{"id": "I_1", "number": 1, "description": "otra"},
                  {"id": "I_2", "number": 2, "description": "x <!-- m:HU-01 --> y", "url": "u"}]
        with patch.object(mcp_projects, "call_tool", return_value=issues) as call:
            found = mcp_projects.find_issue_by_marker("<!-- m:HU-01 -->")
        self.assertEqual(found, {"id": "I_2", "number": 2, "url": "u"})
        self.assertEqual(call.call_args.args[1]["status"], "all")
        with patch.object(mcp_projects, "call_tool", return_value=issues):
            self.assertIsNone(mcp_projects.find_issue_by_marker("<!-- nada -->"))

    def test_target_repo_check_rejects_a_mcp_pointing_elsewhere(self):
        elsewhere = [{"number": 1, "url": "https://github.com/otro/repo/issues/1"}]
        with patch.object(mcp_projects, "call_tool", return_value=elsewhere):
            with self.assertRaisesRegex(RuntimeError, "otro repositorio"):
                mcp_projects.verify_target_repo()
        right = [{"number": 1, "url": mcp_projects.expected_repo_url() + "1"}]
        with patch.object(mcp_projects, "call_tool", return_value=right):
            mcp_projects.verify_target_repo()
        with patch.object(mcp_projects, "call_tool", return_value=[]):
            mcp_projects.verify_target_repo()

if __name__ == "__main__":
    unittest.main()
