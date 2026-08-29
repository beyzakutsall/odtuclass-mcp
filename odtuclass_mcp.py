"""
ODTUClass MCP Server.
Model Context Protocol (MCP) server for METU ODTUClass (Moodle platform).
Implemented using FastMCP for seamless integration with Antigravity AI agents and Claude Desktop.
"""

import sys
import logging
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

from odtuclass_client import ODTUClassAPIError, ODTUClassClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("odtuclass-mcp")

# Initialize FastMCP Server
mcp = FastMCP(
    "odtuclass-mcp",
    dependencies=["httpx", "beautifulsoup4", "pydantic", "python-dateutil"],
)


@mcp.tool()
def login(username: str, password: str) -> Dict[str, Any]:
    """
    Authenticates with METU ODTUClass using student username and password.
    Retrieves and caches the Moodle Web Service token automatically.

    Args:
        username (str): METU student username / user ID (e.g. 'e123456').
        password (str): METU student account password.

    Returns:
        Dict[str, Any]: Authentication result containing:
            - success (bool): True if login succeeded.
            - token (Optional[str]): The acquired 32-character web service token.
            - message (str): Status description.
    """
    logger.info("Attempting login for user '%s'...", username)
    client = ODTUClassClient()
    try:
        token = client.login_with_credentials(username=username, password=password)
        return {
            "success": True,
            "token": token,
            "message": "Successfully logged in to ODTUClass. Token acquired and cached.",
        }
    except ODTUClassAPIError as e:
        logger.error("ODTUClass login error: %s", str(e))
        return {
            "success": False,
            "token": None,
            "error": True,
            "error_code": e.error_code,
            "message": str(e),
        }
    except Exception as e:
        logger.exception("Unexpected error during login")
        return {
            "success": False,
            "token": None,
            "error": True,
            "message": f"Unexpected error during login: {str(e)}",
        }


@mcp.tool()
def get_enrolled_courses(student_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all enrolled courses and course IDs for a student on ODTUClass.

    Args:
        student_token (Optional[str]): The student's ODTUClass Moodle Web Service token.
            Optional if ODTUCLASS_TOKEN, or ODTUCLASS_USERNAME & ODTUCLASS_PASSWORD are set in config/env.

    Returns:
        List[Dict[str, Any]]: List of enrolled course objects containing:
            - id (int): Course ID in ODTUClass.
            - shortname (str): Short course code (e.g., 'CENG140.1', 'MATH119').
            - fullname (str): Full course name (e.g., 'CENG140 C Programming Section 1').
            - idnumber (Optional[str]): Course ID number.
            - summary (Optional[str]): Course description text.
            - course_url (str): Web link to the course homepage.
            - startdate (Optional[int]): Start timestamp.
            - enddate (Optional[int]): End timestamp.
    """
    logger.info("Fetching enrolled courses for student...")
    client = ODTUClassClient()
    try:
        courses = client.get_enrolled_courses(student_token)
        return [course.model_dump() for course in courses]
    except ODTUClassAPIError as e:
        logger.error("ODTUClass API Error in get_enrolled_courses: %s", str(e))
        return [{"error": True, "message": str(e), "error_code": e.error_code}]
    except Exception as e:
        logger.exception("Unexpected error in get_enrolled_courses")
        return [{"error": True, "message": f"Unexpected error: {str(e)}"}]


@mcp.tool()
def get_course_announcements(
    course_id: str,
    student_token: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetches the latest announcements and forum posts from a course on ODTUClass.

    Args:
        course_id (str): The ODTUClass course ID (numeric string or integer, e.g., '12345').
        student_token (Optional[str]): The student's ODTUClass Moodle Web Service token.
            Optional if token or credentials are configured in environment.
        limit (int, optional): Maximum number of announcements to return. Defaults to 5.

    Returns:
        List[Dict[str, Any]]: List of announcements containing:
            - id (int): Post or discussion ID.
            - discussion_id (int): Discussion thread ID.
            - subject (str): Title/subject of the announcement.
            - author_name (str): Instructor or TA who posted.
            - created_at (str): Human-readable creation date & time.
            - modified_at (Optional[str]): Last modified date.
            - message (str): Clean Markdown/text of the announcement content.
            - attachments (List[Dict]): Any attached files with direct download links.
            - discussion_url (str): Direct link to discussion on ODTUClass.
    """
    logger.info("Fetching announcements for course ID %s (limit=%d)...", course_id, limit)
    client = ODTUClassClient()
    try:
        announcements = client.get_course_announcements(course_id, student_token, limit=limit)
        return [ann.model_dump() for ann in announcements]
    except ODTUClassAPIError as e:
        logger.error("ODTUClass API Error in get_course_announcements: %s", str(e))
        return [{"error": True, "message": str(e), "error_code": e.error_code}]
    except Exception as e:
        logger.exception("Unexpected error in get_course_announcements")
        return [{"error": True, "message": f"Unexpected error: {str(e)}"}]


@mcp.tool()
def get_course_syllabus(
    course_id: str,
    student_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Locates and extracts the syllabus, course policy, grading scheme, or outline PDF/text
    from the course's ODTUClass homepage.

    Args:
        course_id (str): The ODTUClass course ID (e.g., '12345').
        student_token (Optional[str]): The student's ODTUClass Moodle Web Service token.
            Optional if token or credentials are configured in environment.

    Returns:
        Dict[str, Any]: Syllabus information object containing:
            - course_id (int): Course ID.
            - syllabus_found (bool): Whether syllabus materials were found.
            - items (List[Dict]): List of identified syllabus documents/pages:
                - title (str): Resource title.
                - type (str): 'file_resource', 'url_link', 'page_content', or 'section_overview'.
                - file_name (Optional[str]): Downloadable filename (e.g. syllabus.pdf).
                - file_url (Optional[str]): Download URL with authentication token.
                - content_summary (Optional[str]): Clean preview text or policy summary.
                - direct_url (Optional[str]): Web link to the resource on ODTUClass.
            - message (str): Status summary message.
    """
    logger.info("Searching syllabus for course ID %s...", course_id)
    client = ODTUClassClient()
    try:
        syllabus_response = client.get_course_syllabus(course_id, student_token)
        return syllabus_response.model_dump()
    except ODTUClassAPIError as e:
        logger.error("ODTUClass API Error in get_course_syllabus: %s", str(e))
        cid_val = int(str(course_id).strip()) if str(course_id).strip().isdigit() else 0
        return {"course_id": cid_val, "syllabus_found": False, "items": [], "error": True, "message": str(e)}
    except Exception as e:
        logger.exception("Unexpected error in get_course_syllabus")
        cid_val = int(str(course_id).strip()) if str(course_id).strip().isdigit() else 0
        return {"course_id": cid_val, "syllabus_found": False, "items": [], "error": True, "message": f"Unexpected error: {str(e)}"}


@mcp.tool()
def get_upcoming_assignments(student_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lists all upcoming assignments, quizzes, and deadlines across all enrolled courses
    with remaining time calculations and submission links.

    Args:
        student_token (Optional[str]): The student's ODTUClass Moodle Web Service token.
            Optional if token or credentials are configured in environment.

    Returns:
        List[Dict[str, Any]]: Chronologically sorted list of deadlines containing:
            - id (int): Assignment/Event ID.
            - name (str): Assignment or quiz title.
            - course_id (int): Associated course ID.
            - course_name (str): Associated course name/code.
            - event_type (str): 'assign', 'quiz', etc.
            - due_timestamp (int): Unix timestamp.
            - due_date_formatted (str): Formatted date and time.
            - time_remaining (str): E.g. 'in 2 days, 4 hours' or 'Overdue by 3 hours'.
            - is_overdue (bool): True if deadline has passed.
            - action_url (Optional[str]): Direct link to submit/view activity.
            - description (Optional[str]): Instructions/description excerpt.
    """
    logger.info("Fetching upcoming assignments and deadlines...")
    client = ODTUClassClient()
    try:
        assignments = client.get_upcoming_assignments(student_token)
        return [ass.model_dump() for ass in assignments]
    except ODTUClassAPIError as e:
        logger.error("ODTUClass API Error in get_upcoming_assignments: %s", str(e))
        return [{"error": True, "message": str(e), "error_code": e.error_code}]
    except Exception as e:
        logger.exception("Unexpected error in get_upcoming_assignments")
        return [{"error": True, "message": f"Unexpected error: {str(e)}"}]


@mcp.tool()
def get_lab_recitation_info(
    course_code: str,
    section: int,
    student_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scans course announcements, weekly schedules, and sections to find the specific
    Lab, Recitation, or Problem Session (PS) hours, room location, and info for a student's section.

    Args:
        course_code (str): Course code (e.g., 'CENG242', 'MATH119') or course ID.
        section (int): Student's section/group number (e.g., 1, 2, 3).
        student_token (Optional[str]): The student's ODTUClass Moodle Web Service token.
            Optional if token or credentials are configured in environment.

    Returns:
        Dict[str, Any]: Lab/Recitation info containing:
            - course_code (str): Course code queried.
            - course_id (Optional[int]): Resolved course ID.
            - course_fullname (Optional[str]): Resolved course title.
            - requested_section (int): Queried section number.
            - found (bool): Whether relevant schedule info was identified.
            - schedule_summary (str): Human-readable summary of timings and locations.
            - schedules (List[Dict]): Matched schedule entries with activity type, day & time, room, and context.
            - relevant_announcements (List[Dict]): Course announcements regarding lab/recitations.
            - related_files_or_links (List[Dict]): Schedule PDF or spreadsheet links if attached.
    """
    logger.info("Searching lab/recitation info for %s Section %d...", course_code, section)
    client = ODTUClassClient()
    try:
        info = client.get_lab_recitation_info(course_code, section, student_token)
        return info.model_dump()
    except ODTUClassAPIError as e:
        logger.error("ODTUClass API Error in get_lab_recitation_info: %s", str(e))
        return {
            "course_code": course_code,
            "requested_section": section,
            "found": False,
            "schedule_summary": f"API Error: {str(e)}",
            "schedules": [],
            "relevant_announcements": [],
            "related_files_or_links": [],
            "error": True,
        }
    except Exception as e:
        logger.exception("Unexpected error in get_lab_recitation_info")
        return {
            "course_code": course_code,
            "requested_section": section,
            "found": False,
            "schedule_summary": f"Unexpected error: {str(e)}",
            "schedules": [],
            "relevant_announcements": [],
            "related_files_or_links": [],
            "error": True,
        }


def main():
    """Main entry point to run the FastMCP server via STDIO."""
    logger.info("Starting ODTUClass FastMCP Server...")
    mcp.run()


if __name__ == "__main__":
    main()
