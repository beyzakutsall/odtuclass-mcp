"""
Unit and Mock Tests for ODTUClass MCP Server and Client.
"""

import os
import unittest
from unittest.mock import MagicMock, patch
import httpx

from models import (
    AnnouncementAttachment,
    AnnouncementItem,
    CourseInfo,
    LabRecitationInfo,
    LabRecitationScheduleEntry,
    SyllabusItem,
    SyllabusResponse,
    UpcomingAssignment,
)
from odtuclass_client import (
    ODTUClassAPIError,
    ODTUClassClient,
    clean_html_to_markdown,
    compute_time_remaining,
    format_timestamp,
)
from odtuclass_mcp import (
    get_enrolled_courses,
    get_course_announcements,
    get_course_syllabus,
    get_upcoming_assignments,
    get_lab_recitation_info,
)


class TestODTUClassUtilities(unittest.TestCase):
    """Test HTML parsing, formatting, and time calculations."""

    def test_clean_html_to_markdown(self):
        html_input = "<p>Welcome to <b>CENG 140</b>!</p><br><p>Please read <a href='http://example.com'>policy</a>.</p><ul><li>HW 1</li><li>HW 2</li></ul>"
        cleaned = clean_html_to_markdown(html_input)
        self.assertIn("Welcome to CENG 140!", cleaned)
        self.assertIn("[policy](http://example.com)", cleaned)
        self.assertIn("- HW 1", cleaned)
        self.assertIn("- HW 2", cleaned)

        # Empty/None input
        self.assertEqual(clean_html_to_markdown(None), "")
        self.assertEqual(clean_html_to_markdown(""), "")

    def test_format_timestamp(self):
        # Numeric timestamp
        ts = 1700000000
        formatted = format_timestamp(ts)
        self.assertIn("2023", formatted)

        # String timestamp
        formatted_str = format_timestamp("1700000000")
        self.assertEqual(formatted, formatted_str)

        # None, empty or negative
        self.assertEqual(format_timestamp(None), "N/A")
        self.assertEqual(format_timestamp(""), "N/A")
        self.assertEqual(format_timestamp(-100), "N/A")
        self.assertEqual(format_timestamp("invalid"), "N/A")

    def test_compute_time_remaining(self):
        import time
        now = time.time()

        # Future days
        rem_str, is_overdue = compute_time_remaining(now + 95000)
        self.assertFalse(is_overdue)
        self.assertIn("in 1 day", rem_str)

        # Future hours
        rem_str_hr, is_overdue_hr = compute_time_remaining(now + 7500)
        self.assertFalse(is_overdue_hr)
        self.assertIn("in 2 hour", rem_str_hr)

        # Future minutes (<1 hour)
        rem_str_min, is_overdue_min = compute_time_remaining(now + 300)
        self.assertFalse(is_overdue_min)
        self.assertIn("minute(s) - URGENT", rem_str_min)

        # Past days
        rem_str_past_days, is_overdue_past_days = compute_time_remaining(now - 95000)
        self.assertTrue(is_overdue_past_days)
        self.assertIn("Overdue by 1 day", rem_str_past_days)

        # Past hours
        rem_str_past_hr, is_overdue_past_hr = compute_time_remaining(now - 4000)
        self.assertTrue(is_overdue_past_hr)
        self.assertIn("Overdue by 1 hour", rem_str_past_hr)

        # Past minutes (<1 hour overdue)
        rem_str_past_min, is_overdue_past_min = compute_time_remaining(now - 600)
        self.assertTrue(is_overdue_past_min)
        self.assertIn("Overdue by 10 min", rem_str_past_min)

        # Invalid timestamp
        rem_invalid, is_overdue_invalid = compute_time_remaining("invalid")
        self.assertEqual(rem_invalid, "Unknown deadline")
        self.assertFalse(is_overdue_invalid)


class TestODTUClassClient(unittest.TestCase):
    """Test ODTUClassClient methods with mocked responses."""

    def setUp(self):
        self.client = ODTUClassClient(base_url="https://odtuclass.metu.edu.tr")
        # Reset any in-memory cached token to avoid cross-test leakage
        self.client._cached_token = None

    @patch.dict("os.environ", {}, clear=False)
    @patch.object(ODTUClassClient, "_load_cached_token", return_value=None)
    def test_missing_token_raises_error(self, _mock_cache):
        # Ensure no env token or credentials are present
        for key in ("ODTUCLASS_TOKEN", "ODTUCLASS_USERNAME", "ODTUCLASS_PASSWORD"):
            os.environ.pop(key, None)
        self.client._cached_token = None
        with self.assertRaises(ODTUClassAPIError) as ctx:
            self.client._execute_ws("core_webservice_get_site_info", "")
        self.assertEqual(ctx.exception.error_code, "missing_token")

    @patch("httpx.Client.post")
    def test_execute_ws_network_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with self.assertRaises(ODTUClassAPIError) as ctx:
            self.client._execute_ws("core_webservice_get_site_info", "fake_token")
        self.assertEqual(ctx.exception.error_code, "network_error")

    @patch("httpx.Client.post")
    def test_execute_ws_moodle_exception(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "exception": "moodle_exception",
            "errorcode": "invalidtoken",
            "message": "Invalid token",
        }
        mock_post.return_value = mock_resp

        with self.assertRaises(ODTUClassAPIError) as ctx:
            self.client._execute_ws("core_webservice_get_site_info", "invalid_token")
        self.assertEqual(ctx.exception.error_code, "invalidtoken")
        self.assertIn("Invalid student token", str(ctx.exception))

    @patch.object(ODTUClassClient, "_execute_ws")
    def test_get_enrolled_courses(self, mock_ws):
        # Mock site info then user courses
        mock_ws.side_effect = [
            {"userid": 42, "fullname": "Test Student"},
            [
                {
                    "id": 101,
                    "shortname": "CENG140.1",
                    "fullname": "CENG140 C Programming Section 1",
                    "summary": "<p>Intro to C programming course.</p>",
                }
            ],
        ]

        courses = self.client.get_enrolled_courses("fake_token")
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].id, 101)
        self.assertEqual(courses[0].shortname, "CENG140.1")
        self.assertEqual(courses[0].course_url, f"{self.client.base_url}/course/view.php?id=101")

    @patch.object(ODTUClassClient, "_execute_ws")
    def test_get_course_announcements(self, mock_ws):
        # Mock forums then discussions
        mock_ws.side_effect = [
            [{"id": 55, "name": "Announcements", "type": "news"}],
            {
                "discussions": [
                    {
                        "id": 1,
                        "discussion": 1001,
                        "subject": "Midterm Date Announced",
                        "userfullname": "Dr. Instructor",
                        "created": 1700000000,
                        "message": "<p>Midterm will be next week.</p>",
                        "attachments": [
                            {
                                "filename": "midterm_info.pdf",
                                "fileurl": "https://odtuclass.metu.edu.tr/pluginfile.php/1/info.pdf",
                            }
                        ],
                    }
                ]
            },
        ]

        announcements = self.client.get_course_announcements(101, "fake_token")
        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].subject, "Midterm Date Announced")
        self.assertIn("Midterm will be next week.", announcements[0].message)
        self.assertEqual(len(announcements[0].attachments), 1)
        self.assertIn("token=fake_token", announcements[0].attachments[0].fileurl)

    @patch.object(ODTUClassClient, "_execute_ws")
    def test_get_course_syllabus(self, mock_ws):
        mock_ws.return_value = [
            {
                "id": 1,
                "name": "General",
                "summary": "Course intro",
                "modules": [
                    {
                        "id": 10,
                        "name": "Course Syllabus PDF",
                        "modname": "resource",
                        "contents": [
                            {
                                "filename": "Syllabus_Spring2026.pdf",
                                "fileurl": "https://odtuclass.metu.edu.tr/pluginfile.php/1/syllabus.pdf",
                            }
                        ],
                    }
                ],
            }
        ]

        syllabus = self.client.get_course_syllabus(101, "fake_token")
        self.assertTrue(syllabus.syllabus_found)
        self.assertEqual(len(syllabus.items), 1)
        self.assertEqual(syllabus.items[0].file_name, "Syllabus_Spring2026.pdf")

    @patch.object(ODTUClassClient, "_execute_ws")
    def test_get_upcoming_assignments(self, mock_ws):
        import time
        future_ts = int(time.time()) + 86400 * 2

        # Mock calendar action events and mod_assign
        mock_ws.side_effect = [
            {
                "events": [
                    {
                        "id": 501,
                        "name": "Programming HW 1",
                        "course": {"id": 101, "fullname": "CENG140"},
                        "eventtype": "assign",
                        "timestart": future_ts,
                        "action": {"url": "https://odtuclass.metu.edu.tr/mod/assign/view.php?id=123"},
                        "description": "<p>Implement binary tree in C.</p>",
                    }
                ]
            },
            {
                "courses": [
                    {
                        "id": 101,
                        "fullname": "CENG140",
                        "assignments": [
                            {
                                "id": 701,
                                "name": "Lab 1 Submission",
                                "duedate": future_ts + 3600,
                                "cmid": 999,
                                "intro": "<p>Submit your code.</p>",
                            }
                        ],
                    }
                ]
            },
        ]

        assignments = self.client.get_upcoming_assignments("fake_token")
        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0].name, "Programming HW 1")
        self.assertEqual(assignments[1].name, "Lab 1 Submission")
        self.assertFalse(assignments[0].is_overdue)

    @patch.object(ODTUClassClient, "get_enrolled_courses")
    @patch.object(ODTUClassClient, "get_course_announcements")
    @patch.object(ODTUClassClient, "_execute_ws")
    def test_get_lab_recitation_info(self, mock_ws, mock_ann, mock_courses):
        mock_courses.return_value = [
            CourseInfo(
                id=202,
                shortname="CENG242",
                fullname="Programming Language Concepts",
                course_url="https://odtuclass.metu.edu.tr/course/view.php?id=202",
            )
        ]
        mock_ann.return_value = [
            AnnouncementItem(
                id=1,
                discussion_id=1,
                subject="Lab Schedule for Section 1 and Section 2",
                author_name="TA Jane",
                created_at="2026-08-29",
                message="Section 1 Lab is on Monday 13:40 - 15:30 in BMB-1.",
                discussion_url="https://odtuclass.metu.edu.tr/mod/forum/discuss.php?d=1",
            )
        ]
        mock_ws.return_value = []

        info = self.client.get_lab_recitation_info("CENG242", 1, "fake_token")
        self.assertTrue(info.found)
        self.assertEqual(info.requested_section, 1)
        self.assertIn("Section 1", info.schedule_summary)
        self.assertEqual(len(info.schedules), 1)
        self.assertIn("13:40 - 15:30", info.schedules[0].day_and_time)
        self.assertIn("BMB-1", info.schedules[0].location_or_room)


    @patch("httpx.Client.post")
    def test_login_with_credentials_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"token": "1234567890abcdef1234567890abcdef"}
        mock_post.return_value = mock_resp

        token = self.client.login_with_credentials("e123456", "secret_pass")
        self.assertEqual(token, "1234567890abcdef1234567890abcdef")
        self.assertEqual(self.client._cached_token, "1234567890abcdef1234567890abcdef")

    @patch("httpx.Client.post")
    def test_login_with_credentials_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"error": "Invalid login", "errorcode": "invalidlogin"}
        mock_post.return_value = mock_resp

        with self.assertRaises(ODTUClassAPIError) as ctx:
            self.client.login_with_credentials("e123456", "wrong_pass")
        self.assertEqual(ctx.exception.error_code, "invalidlogin")


class TestMCPTools(unittest.TestCase):
    """Test FastMCP tool wrapper functions."""

    @patch.object(ODTUClassClient, "login_with_credentials")
    def test_login_tool_success(self, mock_login):
        mock_login.return_value = "tok123"
        from odtuclass_mcp import login
        res = login("e123456", "password123")
        self.assertTrue(res["success"])
        self.assertEqual(res["token"], "tok123")

    @patch.object(ODTUClassClient, "login_with_credentials")
    def test_login_tool_failure(self, mock_login):
        mock_login.side_effect = ODTUClassAPIError("Invalid credentials", error_code="invalidlogin")
        from odtuclass_mcp import login
        res = login("e123456", "wrong")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "invalidlogin")

    @patch.object(ODTUClassClient, "get_enrolled_courses")
    def test_get_enrolled_courses_tool(self, mock_client_call):
        mock_client_call.return_value = [
            CourseInfo(
                id=1,
                shortname="MATH119",
                fullname="Calculus with Analytic Geometry",
                course_url="https://odtuclass.metu.edu.tr/course/view.php?id=1",
            )
        ]
        res = get_enrolled_courses("test_token")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["shortname"], "MATH119")

    @patch.object(ODTUClassClient, "get_course_announcements")
    def test_get_course_announcements_tool(self, mock_client_call):
        mock_client_call.return_value = [
            AnnouncementItem(
                id=10,
                discussion_id=20,
                subject="Welcome",
                author_name="Prof",
                created_at="2026-08-29",
                message="Welcome students",
                discussion_url="https://odtuclass.metu.edu.tr",
            )
        ]
        res = get_course_announcements("101", "test_token")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["subject"], "Welcome")

    @patch.object(ODTUClassClient, "get_course_syllabus")
    def test_get_course_syllabus_tool(self, mock_client_call):
        mock_client_call.return_value = SyllabusResponse(
            course_id=101,
            syllabus_found=True,
            items=[],
            message="Found syllabus",
        )
        res = get_course_syllabus("101", "test_token")
        self.assertEqual(res["course_id"], 101)
        self.assertTrue(res["syllabus_found"])

    @patch.object(ODTUClassClient, "get_upcoming_assignments")
    def test_get_upcoming_assignments_tool(self, mock_client_call):
        mock_client_call.return_value = [
            UpcomingAssignment(
                id=1,
                name="HW1",
                course_id=101,
                course_name="CENG140",
                event_type="assign",
                due_timestamp=1700000000,
                due_date_formatted="2023-11-14",
                time_remaining="in 2 days",
            )
        ]
        res = get_upcoming_assignments("test_token")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "HW1")

    @patch.object(ODTUClassClient, "get_lab_recitation_info")
    def test_get_lab_recitation_info_tool(self, mock_client_call):
        mock_client_call.return_value = LabRecitationInfo(
            course_code="CENG242",
            course_id=202,
            course_fullname="Programming Language Concepts",
            requested_section=1,
            found=True,
            schedule_summary="Monday 13:40 in BMB-1",
        )
        res = get_lab_recitation_info("CENG242", 1, "test_token")
        self.assertTrue(res["found"])
        self.assertEqual(res["requested_section"], 1)

    @patch.object(ODTUClassClient, "get_enrolled_courses")
    def test_error_handling_in_tools(self, mock_client_call):
        mock_client_call.side_effect = ODTUClassAPIError("Invalid token", error_code="invalidtoken")
        res = get_enrolled_courses("bad_token")
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["error"])
        self.assertEqual(res[0]["error_code"], "invalidtoken")


if __name__ == "__main__":
    unittest.main()
