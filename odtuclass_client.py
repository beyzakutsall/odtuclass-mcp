"""
ODTUClass Moodle REST Web Service API Client.
Handles all network communication, token validation, error parsing,
HTML sanitization, and data extraction for ODTUClass (odtuclass.metu.edu.tr).
"""

import os
import re
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from bs4 import BeautifulSoup

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

DEFAULT_ODTUCLASS_URL = "https://odtuclass.metu.edu.tr"


def load_dotenv_if_present() -> None:
    """Lightweight loader for .env and .env.local files without external dependencies."""
    for filename in [".env.local", ".env"]:
        filepath = os.path.join(os.getcwd(), filename)
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


# Automatically load local .env if present
load_dotenv_if_present()


class ODTUClassAPIError(Exception):
    """Exception raised when ODTUClass Moodle API returns an error."""

    def __init__(self, message: str, error_code: Optional[str] = None, raw_response: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.raw_response = raw_response

    def __str__(self) -> str:
        if self.error_code:
            return f"ODTUClass API Error [{self.error_code}]: {self.message}"
        return f"ODTUClass API Error: {self.message}"


def clean_html_to_markdown(html_text: Optional[str]) -> str:
    """Converts HTML content to clean, readable plain text / Markdown."""
    if not html_text:
        return ""

    # Unescape HTML entities
    unescaped = html.unescape(html_text)
    soup = BeautifulSoup(unescaped, "html.parser")

    # Replace <br> and <p> with newlines
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for p in soup.find_all(["p", "div"]):
        p.insert_after("\n")

    # Replace links with markdown links
    for a in soup.find_all("a", href=True):
        link_text = a.get_text().strip() or a["href"]
        a.replace_with(f"[{link_text}]({a['href']})")

    # Replace list items with markdown bullets
    for li in soup.find_all("li"):
        li_text = li.get_text().strip()
        li.replace_with(f"- {li_text}\n")

    text = soup.get_text()
    # Normalize multiple newlines and spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_timestamp(ts: Optional[Union[int, float, str]]) -> str:
    """Formats unix timestamp into ISO / human readable string."""
    if ts is None or ts == "":
        return "N/A"
    try:
        ts_val = float(ts)
    except (ValueError, TypeError):
        return "N/A"
    if ts_val <= 0:
        return "N/A"
    dt = datetime.fromtimestamp(ts_val, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S (%A)")


def compute_time_remaining(due_ts: Union[int, float, str]) -> Tuple[str, bool]:
    """
    Computes human-friendly remaining time from current timestamp.
    Returns (remaining_string, is_overdue).
    """
    try:
        ts_val = float(due_ts)
    except (ValueError, TypeError):
        return "Unknown deadline", False

    now_ts = datetime.now().timestamp()
    diff = ts_val - now_ts

    if diff < 0:
        overdue_sec = abs(diff)
        days = int(overdue_sec // 86400)
        hours = int((overdue_sec % 86400) // 3600)
        minutes = int((overdue_sec % 3600) // 60)
        if days > 0:
            return f"Overdue by {days} day(s), {hours} hour(s)", True
        elif hours > 0:
            return f"Overdue by {hours} hour(s), {minutes} min(s)", True
        else:
            return f"Overdue by {minutes} min(s)", True

    days = int(diff // 86400)
    hours = int((diff % 86400) // 3600)
    minutes = int((diff % 3600) // 60)

    if days > 0:
        return f"in {days} day(s), {hours} hour(s)", False
    elif hours > 0:
        return f"in {hours} hour(s), {minutes} min(s)", False
    else:
        return f"in {minutes} minute(s) - URGENT", False


class ODTUClassClient:
    """Client for querying ODTUClass Moodle REST Web Services."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 20.0):
        raw_url = (base_url or os.getenv("ODTUCLASS_BASE_URL") or DEFAULT_ODTUCLASS_URL).rstrip("/")
        self.raw_base_url = raw_url
        self._resolved_base_url: Optional[str] = None
        self.timeout = timeout
        self._cached_token: Optional[str] = None

    @property
    def cache_dir(self) -> str:
        """Directory used for storing secure, gitignored session tokens."""
        d = os.path.join(os.getcwd(), ".odtuclass_cache")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def downloads_dir(self) -> str:
        """Dedicated, gitignored folder for all downloaded syllabus and course materials."""
        d = os.path.join(os.getcwd(), "downloads")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def base_url(self) -> str:
        """
        Returns the resolved base URL, automatically following semester redirects
        (e.g., https://odtuclass.metu.edu.tr -> https://odtuclass2025sum.metu.edu.tr).
        """
        if self._resolved_base_url is None:
            self._resolved_base_url = self._discover_base_url(self.raw_base_url)
        return self._resolved_base_url

    @base_url.setter
    def base_url(self, value: str):
        self.raw_base_url = value.rstrip("/")
        self._resolved_base_url = value.rstrip("/")

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/webservice/rest/server.php"

    @property
    def token_endpoint(self) -> str:
        return f"{self.base_url}/login/token.php"

    def _discover_base_url(self, target_url: str) -> str:
        """
        Follows initial GET redirects to discover the active semester subdomain.
        """
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                res = client.get(target_url)
                final_url = str(res.url).rstrip("/")
                if final_url.startswith("http://"):
                    final_url = "https://" + final_url[len("http://"):]
                return final_url
        except Exception:
            return target_url

    def _save_session(self, token: str, username: Optional[str] = None) -> None:
        """
        Saves only the session token (never the password) into a gitignored local cache file.
        """
        import json
        session_file = os.path.join(self.cache_dir, "session.json")
        try:
            data = {
                "token": token,
                "username": username or "",
                "base_url": self.base_url,
                "saved_at": int(datetime.now().timestamp()),
            }
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_cached_token(self) -> Optional[str]:
        """Loads cached session token from local cache file if available."""
        import json
        session_file = os.path.join(self.cache_dir, "session.json")
        if os.path.isfile(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tok = data.get("token")
                    if tok and isinstance(tok, str) and len(tok) >= 16:
                        return tok.strip()
            except Exception:
                pass
        return None

    def download_file(
        self,
        file_url: str,
        filename: Optional[str] = None,
        subfolder: Optional[str] = None,
        student_token: Optional[str] = None,
    ) -> str:
        """
        Downloads a course file, attachment, or syllabus directly into the dedicated,
        gitignored downloads/ directory.

        Args:
            file_url (str): The file download URL.
            filename (Optional[str]): Desired local file name.
            subfolder (Optional[str]): Optional subfolder (e.g. 'MATH130' or 'Syllabus').
            student_token (Optional[str]): Token for authentication.

        Returns:
            str: Absolute path to the downloaded file.
        """
        token = self._resolve_token(student_token)
        url = file_url
        if token and "token=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={token}"

        target_dir = self.downloads_dir
        if subfolder:
            clean_sub = re.sub(r'[\\/*?:"<>|]', "_", subfolder).strip()
            target_dir = os.path.join(target_dir, clean_sub)
            os.makedirs(target_dir, exist_ok=True)

        if not filename:
            parsed_name = url.split("?")[0].split("/")[-1]
            filename = parsed_name or "downloaded_file"

        clean_filename = re.sub(r'[\\/*?:"<>|]', "_", filename).strip() or "downloaded_file"
        save_path = os.path.join(target_dir, clean_filename)

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(response.content)

        return save_path

    def login_with_credentials(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        service: str = "moodle_mobile_app",
    ) -> str:
        """
        Authenticates against ODTUClass using student username and password via /login/token.php.
        Returns the generated Moodle Web Service token and caches it safely.
        """
        user = (username or os.getenv("ODTUCLASS_USERNAME") or "").strip()
        pwd = (password or os.getenv("ODTUCLASS_PASSWORD") or "").strip()

        if not user or not pwd:
            raise ODTUClassAPIError(
                "Username and password are required for login. Please provide credentials or set ODTUCLASS_USERNAME and ODTUCLASS_PASSWORD.",
                error_code="missing_credentials",
            )

        payload = {
            "username": user,
            "password": pwd,
            "service": service,
        }

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.post(self.token_endpoint, data=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise ODTUClassAPIError(
                f"HTTP error {e.response.status_code} while authenticating with ODTUClass: {str(e)}",
                error_code="http_error",
            ) from e
        except httpx.RequestError as e:
            raise ODTUClassAPIError(
                f"Network connection failed while contacting ODTUClass login ({self.token_endpoint}): {str(e)}",
                error_code="network_error",
            ) from e
        except ValueError as e:
            raise ODTUClassAPIError(
                f"Failed to parse JSON response from ODTUClass login: {str(e)}",
                error_code="invalid_json",
            ) from e

        if isinstance(data, dict):
            if "error" in data or "errorcode" in data:
                error_msg = data.get("error") or data.get("message") or "Authentication failed."
                error_code = data.get("errorcode", "auth_failed")
                if error_code == "invalidlogin":
                    error_msg = "Invalid ODTUClass username or password. Please check your credentials."
                raise ODTUClassAPIError(error_msg, error_code=error_code, raw_response=data)

            token = data.get("token")
            if token:
                self._cached_token = str(token).strip()
                self._save_session(self._cached_token, username=user)
                return self._cached_token

        raise ODTUClassAPIError("No token returned from ODTUClass login endpoint.", raw_response=data)

    def _resolve_token(self, student_token: Optional[str] = None) -> str:
        """
        Resolves the student token from argument, environment variable, cached session,
        or attempts automatic login if ODTUCLASS_USERNAME and ODTUCLASS_PASSWORD are set.
        """
        token = (student_token or os.getenv("ODTUCLASS_TOKEN") or self._cached_token or "").strip()
        if token:
            return token

        # Check local session file
        cached_file_tok = self._load_cached_token()
        if cached_file_tok:
            self._cached_token = cached_file_tok
            return cached_file_tok

        # If credentials exist in environment variables, auto-login
        if os.getenv("ODTUCLASS_USERNAME") and os.getenv("ODTUCLASS_PASSWORD"):
            return self.login_with_credentials()

        return ""

    def _execute_ws(
        self,
        wsfunction: str,
        student_token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Executes a Moodle REST Web Service call.
        Raises ODTUClassAPIError on Moodle API exception or invalid response.
        """
        token = self._resolve_token(student_token)
        if not token:
            raise ODTUClassAPIError(
                "Student token is missing. Please provide an ODTUClass Web Service token, or set ODTUCLASS_TOKEN / ODTUCLASS_USERNAME / ODTUCLASS_PASSWORD.",
                error_code="missing_token",
            )

        payload: Dict[str, Any] = {
            "wstoken": token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
        }

        if params:
            payload.update(params)

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.post(self.endpoint, data=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise ODTUClassAPIError(
                f"HTTP error {e.response.status_code} while connecting to ODTUClass: {str(e)}",
                error_code="http_error",
            ) from e
        except httpx.RequestError as e:
            raise ODTUClassAPIError(
                f"Network connection failed while contacting ODTUClass ({self.base_url}): {str(e)}",
                error_code="network_error",
            ) from e
        except ValueError as e:
            raise ODTUClassAPIError(
                f"Failed to parse JSON response from ODTUClass: {str(e)}",
                error_code="invalid_json",
            ) from e

        # Check for Moodle API Exception object
        if isinstance(data, dict):
            if "exception" in data or "errorcode" in data:
                error_msg = data.get("message") or data.get("error") or "Unknown Moodle error"
                error_code = data.get("errorcode", "moodle_exception")
                if error_code == "invalidtoken":
                    error_msg = (
                        "Invalid student token. Please check your ODTUClass Web Services token in your profile settings."
                    )
                elif error_code == "accessexception":
                    error_msg = (
                        "Access denied. Your token does not have permission for this web service function or course."
                    )
                raise ODTUClassAPIError(error_msg, error_code=error_code, raw_response=data)

        return data

    def get_site_info(self, student_token: Optional[str] = None) -> Dict[str, Any]:
        """Gets site info and current authenticated user details."""
        return self._execute_ws("core_webservice_get_site_info", student_token)

    def get_enrolled_courses(self, student_token: Optional[str] = None) -> List[CourseInfo]:
        """
        Retrieves all courses the student is currently enrolled in on ODTUClass.
        Uses core_webservice_get_site_info to discover userid, then core_enrol_get_users_courses.
        """
        site_info = self.get_site_info(student_token)
        user_id = site_info.get("userid")
        if not user_id:
            raise ODTUClassAPIError("Could not retrieve user ID from ODTUClass site info.")

        raw_courses = self._execute_ws(
            "core_enrol_get_users_courses",
            student_token,
            {"userid": user_id},
        )

        if not isinstance(raw_courses, list):
            return []

        courses: List[CourseInfo] = []
        for c in raw_courses:
            course_id = c.get("id")
            if not course_id:
                continue

            course_url = f"{self.base_url}/course/view.php?id={course_id}"
            summary_clean = clean_html_to_markdown(c.get("summary"))

            courses.append(
                CourseInfo(
                    id=course_id,
                    shortname=c.get("shortname", ""),
                    fullname=c.get("fullname", ""),
                    idnumber=c.get("idnumber"),
                    summary=summary_clean or None,
                    course_url=course_url,
                    startdate=c.get("startdate"),
                    enddate=c.get("enddate"),
                    enrolled_student_count=c.get("enrolledusercount"),
                )
            )

        return courses

    def get_course_announcements(
        self,
        course_id: Union[str, int],
        student_token: Optional[str] = None,
        limit: int = 5,
    ) -> List[AnnouncementItem]:
        """
        Fetches the latest announcements from the course's announcements forum.
        """
        cid = int(course_id)
        # Step 1: Find forums in this course
        forums_data = self._execute_ws(
            "mod_forum_get_forums_by_courses",
            student_token,
            {"courseids[0]": cid},
        )

        if not isinstance(forums_data, list) or not forums_data:
            return []

        # Find announcement / news forum
        announcement_forum = None
        for forum in forums_data:
            forum_type = forum.get("type", "")
            forum_name = (forum.get("name") or "").lower()
            if forum_type == "news" or "announcement" in forum_name or "duyuru" in forum_name:
                announcement_forum = forum
                break

        if not announcement_forum:
            # Fallback to the first forum found
            announcement_forum = forums_data[0]

        forum_id = announcement_forum.get("id")
        if not forum_id:
            return []

        # Step 2: Get discussions
        discussions_data = self._execute_ws(
            "mod_forum_get_forum_discussions",
            student_token,
            {"forumid": forum_id, "sortorder": 6},  # 6 = newest first
        )

        discussions = []
        if isinstance(discussions_data, dict) and "discussions" in discussions_data:
            discussions = discussions_data["discussions"]
        elif isinstance(discussions_data, list):
            discussions = discussions_data

        # Limit items
        discussions = discussions[:limit]

        announcements: List[AnnouncementItem] = []
        for disc in discussions:
            disc_id = disc.get("discussion", disc.get("id", 0))
            disc_url = f"{self.base_url}/mod/forum/discuss.php?d={disc_id}"
            
            # Format message
            raw_msg = disc.get("message", "")
            clean_msg = clean_html_to_markdown(raw_msg)

            # Process attachments
            attachments_list: List[AnnouncementAttachment] = []
            raw_attachments = disc.get("attachments")
            if isinstance(raw_attachments, list):
                for att in raw_attachments:
                    if not isinstance(att, dict):
                        continue
                    file_url = att.get("fileurl", "")
                    if file_url and "token=" not in file_url:
                        # Append token for direct authenticated download if needed
                        token = self._resolve_token(student_token)
                        sep = "&" if "?" in file_url else "?"
                        file_url = f"{file_url}{sep}token={token}"

                    attachments_list.append(
                        AnnouncementAttachment(
                            filename=att.get("filename", "attachment"),
                            fileurl=file_url,
                            filesize=att.get("filesize"),
                            mimetype=att.get("mimetype"),
                        )
                    )

            created_str = format_timestamp(disc.get("created"))
            modified_str = format_timestamp(disc.get("modified"))

            announcements.append(
                AnnouncementItem(
                    id=disc.get("id", disc_id),
                    discussion_id=disc_id,
                    subject=disc.get("subject") or disc.get("name", "Untitled Announcement"),
                    author_name=disc.get("userfullname") or disc.get("author", "Instructor / TA"),
                    created_at=created_str,
                    modified_at=modified_str if modified_str != created_str else None,
                    message=clean_msg,
                    attachments=attachments_list,
                    discussion_url=disc_url,
                )
            )

        return announcements

    def get_course_syllabus(
        self,
        course_id: Union[str, int],
        student_token: Optional[str] = None,
    ) -> SyllabusResponse:
        """
        Inspects course sections, modules, and resources to find Syllabus,
        Course Outline, or Policy documents/pages.
        """
        cid = int(course_id)
        contents = self._execute_ws(
            "core_course_get_contents",
            student_token,
            {"courseid": cid},
        )

        if not isinstance(contents, list):
            return SyllabusResponse(
                course_id=cid,
                syllabus_found=False,
                items=[],
                message="No course contents available or course ID invalid.",
            )

        syllabus_keywords = [
            "syllabus",
            "izlence",
            "izlencesi",
            "course outline",
            "course information",
            "course policy",
            "grading policy",
            "ders izlencesi",
            "ders programı",
            "general information",
            "course overview",
        ]

        items: List[SyllabusItem] = []

        # Scan all sections and their modules
        for section in contents:
            section_name = (section.get("name") or "").strip()
            section_summary = clean_html_to_markdown(section.get("summary"))

            # Check if section itself is named Syllabus
            section_matches = any(k in section_name.lower() for k in syllabus_keywords)
            if section_matches and section_summary:
                items.append(
                    SyllabusItem(
                        course_id=cid,
                        title=f"Section: {section_name}",
                        type="section_overview",
                        content_summary=section_summary[:1000],
                        direct_url=f"{self.base_url}/course/view.php?id={cid}#section-{section.get('section', 0)}",
                    )
                )

            modules = section.get("modules", [])
            for mod in modules:
                mod_name = (mod.get("name") or "").strip()
                mod_type = mod.get("modname", "")
                mod_url = mod.get("url") or f"{self.base_url}/mod/{mod_type}/view.php?id={mod.get('id')}"
                mod_desc = clean_html_to_markdown(mod.get("description"))

                # Check if module matches keywords
                mod_matches = any(k in mod_name.lower() for k in syllabus_keywords)

                # Check contents inside module (e.g. PDF/DOCX files)
                mod_contents = mod.get("contents", [])
                file_found = False
                for c_item in mod_contents:
                    file_name = c_item.get("filename", "")
                    file_url = c_item.get("fileurl", "")
                    if file_url and "token=" not in file_url:
                        token = self._resolve_token(student_token)
                        sep = "&" if "?" in file_url else "?"
                        file_url = f"{file_url}{sep}token={token}"

                    file_matches = any(k in file_name.lower() for k in syllabus_keywords)
                    if mod_matches or file_matches:
                        file_found = True
                        items.append(
                            SyllabusItem(
                                course_id=cid,
                                title=mod_name or file_name,
                                type="file_resource",
                                file_name=file_name,
                                file_url=file_url,
                                content_summary=mod_desc or f"Downloadable file: {file_name}",
                                direct_url=mod_url,
                            )
                        )

                if not file_found and mod_matches:
                    # Could be a page, URL or label
                    items.append(
                        SyllabusItem(
                            course_id=cid,
                            title=mod_name,
                            type="page_content" if mod_type == "page" else "url_link",
                            content_summary=mod_desc or f"Course module: {mod_name} ({mod_type})",
                            direct_url=mod_url,
                        )
                    )

        # Fallback: if no direct keyword match, inspect Section 0 (General)
        if not items and contents:
            section_0 = contents[0]
            sec0_summary = clean_html_to_markdown(section_0.get("summary"))
            sec0_modules = section_0.get("modules", [])

            fallback_links = []
            for mod in sec0_modules[:5]:
                m_name = mod.get("name", "")
                m_type = mod.get("modname", "")
                m_url = mod.get("url") or f"{self.base_url}/mod/{m_type}/view.php?id={mod.get('id')}"
                fallback_links.append(f"- [{m_name}]({m_url}) ({m_type})")

            summary_text = sec0_summary if sec0_summary else "General introductory resources:"
            if fallback_links:
                summary_text += "\n\nGeneral section resources:\n" + "\n".join(fallback_links)

            items.append(
                SyllabusItem(
                    course_id=cid,
                    title="General Course Overview (Section 0)",
                    type="section_overview",
                    content_summary=summary_text[:1200],
                    direct_url=f"{self.base_url}/course/view.php?id={cid}",
                )
            )

        found = len(items) > 0
        status_msg = (
            f"Successfully found {len(items)} syllabus/course outline resource(s)."
            if found
            else "No syllabus or course policy resources found on course page."
        )

        return SyllabusResponse(
            course_id=cid,
            syllabus_found=found,
            items=items,
            message=status_msg,
        )

    def get_upcoming_assignments(self, student_token: Optional[str] = None) -> List[UpcomingAssignment]:
        """
        Fetches all upcoming assignments, quizzes, and deadlines from Moodle Calendar
        and Assignment Web Services.
        """
        now_ts = int(datetime.now().timestamp())
        assignments_map: Dict[str, UpcomingAssignment] = {}

        # 1. Query core_calendar_get_action_events_by_timesort
        try:
            cal_events = self._execute_ws(
                "core_calendar_get_action_events_by_timesort",
                student_token,
                {"timesortfrom": now_ts - 86400, "limitnum": 30},  # include recent 1 day to catch today
            )
            events = cal_events.get("events", []) if isinstance(cal_events, dict) else []
            if isinstance(events, list):
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    ev_id = ev.get("id", 0)
                    ev_name = ev.get("name", "Untitled Event")
                    course_info = ev.get("course") if isinstance(ev.get("course"), dict) else {}
                    course_id = course_info.get("id", 0)
                    course_name = course_info.get("fullname") or course_info.get("shortname", "Unknown Course")

                    due_ts = ev.get("timesort") or ev.get("timestart") or 0
                    try:
                        due_ts = int(due_ts)
                    except (ValueError, TypeError):
                        due_ts = 0

                    remaining_str, is_overdue = compute_time_remaining(due_ts)
                    action_data = ev.get("action")
                    action_url = (action_data.get("url") if isinstance(action_data, dict) else None) or ev.get("url")
                    clean_desc = clean_html_to_markdown(ev.get("description"))

                    key = f"cal_{course_id}_{ev_name}_{due_ts}"
                    assignments_map[key] = UpcomingAssignment(
                        id=int(ev_id) if str(ev_id).isdigit() else 0,
                        name=str(ev_name),
                        course_id=int(course_id) if str(course_id).isdigit() else 0,
                        course_name=str(course_name),
                        event_type=str(ev.get("eventtype", "assignment")),
                        due_timestamp=due_ts,
                        due_date_formatted=format_timestamp(due_ts),
                        time_remaining=remaining_str,
                        is_overdue=is_overdue,
                        action_url=action_url,
                        description=clean_desc[:500] if clean_desc else None,
                    )
        except Exception:
            # Fallback will continue
            pass

        # 2. Query mod_assign_get_assignments
        try:
            assign_data = self._execute_ws("mod_assign_get_assignments", student_token)
            courses = assign_data.get("courses", []) if isinstance(assign_data, dict) else []
            if isinstance(courses, list):
                for c in courses:
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("id", 0)
                    cname = c.get("fullname") or c.get("shortname", "Course")
                    c_assignments = c.get("assignments")
                    if isinstance(c_assignments, list):
                        for ass in c_assignments:
                            if not isinstance(ass, dict):
                                continue
                            due_date = ass.get("duedate", 0)
                            try:
                                due_date = int(due_date)
                            except (ValueError, TypeError):
                                due_date = 0
                            # Filter for future or recent assignments
                            if due_date and due_date >= (now_ts - 86400 * 3):
                                ass_id = ass.get("id", 0)
                                ass_name = ass.get("name", "Assignment")
                                rem_str, overdue = compute_time_remaining(due_date)
                                act_url = f"{self.base_url}/mod/assign/view.php?id={ass.get('cmid', ass_id)}"
                                clean_intro = clean_html_to_markdown(ass.get("intro"))

                                key = f"ass_{cid}_{ass_name}_{due_date}"
                                if key not in assignments_map:
                                    assignments_map[key] = UpcomingAssignment(
                                        id=int(ass_id) if str(ass_id).isdigit() else 0,
                                        name=str(ass_name),
                                        course_id=int(cid) if str(cid).isdigit() else 0,
                                        course_name=str(cname),
                                        event_type="assign",
                                        due_timestamp=due_date,
                                        due_date_formatted=format_timestamp(due_date),
                                        time_remaining=rem_str,
                                        is_overdue=overdue,
                                        action_url=act_url,
                                        description=clean_intro[:500] if clean_intro else None,
                                    )
        except Exception:
            pass

        # Sort by due_timestamp ascending
        result = list(assignments_map.values())
        result.sort(key=lambda x: x.due_timestamp)
        return result

    def get_lab_recitation_info(
        self,
        course_code: str,
        section: int,
        student_token: Optional[str] = None,
    ) -> LabRecitationInfo:
        """
        Scans course contents, syllabus, and announcements for Lab/Recitation/PS/Workshop
        schedules matching the specified section number.
        """
        # Step 1: Find course ID from course_code
        course_id: Optional[int] = None
        course_fullname: Optional[str] = None

        str_code = str(course_code).strip()
        courses = self.get_enrolled_courses(student_token)
        clean_target = re.sub(r"[\s\-_.]+", "", str_code).upper()
        for c in courses:
            if str(c.id) == str_code:
                course_id = c.id
                course_fullname = c.fullname
                break
            c_short = re.sub(r"[\s\-_.]+", "", c.shortname).upper()
            c_full = re.sub(r"[\s\-_.]+", "", c.fullname).upper()
            if clean_target in c_short or clean_target in c_full:
                course_id = c.id
                course_fullname = c.fullname
                break

        if not course_id and str_code.isdigit():
            course_id = int(str_code)

        if not course_id:
            return LabRecitationInfo(
                course_code=course_code,
                requested_section=section,
                found=False,
                schedule_summary=f"Could not find course '{course_code}' in student's enrolled courses.",
            )

        # Step 2: Retrieve contents & announcements
        contents = self._execute_ws(
            "core_course_get_contents",
            student_token,
            {"courseid": course_id},
        )
        announcements = self.get_course_announcements(course_id, student_token, limit=20)

        # Patterns for lab & recitation keywords
        keywords = ["lab", "recitation", "problem session", "ps", "workshop", "uygulama", "laboratuvar"]
        # Section patterns e.g., "Section 1", "Sec 1", "Sec. 1", "S1", "Group 1", "Grup 1", "Recitation 1", "Lab 1"
        section_patterns = [
            rf"\bsection\s*{section}\b",
            rf"\bsec\.?\s*{section}\b",
            rf"\bgroup\s*{section}\b",
            rf"\bgrup\s*{section}\b",
            rf"\brecitation\s*{section}\b",
            rf"\blab\s*{section}\b",
            rf"\bgr\.?\s*{section}\b",
            rf"\bşube\s*{section}\b",
            rf"\bsube\s*{section}\b",
        ]

        schedules: List[LabRecitationScheduleEntry] = []
        relevant_announcements: List[AnnouncementItem] = []
        related_files: List[Dict[str, Any]] = []

        # Time/day regex pattern (e.g. "Monday 13:40 - 15:30", "Pazartesi 09:40", "13:40-15:30")
        time_pattern = re.compile(
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Pazartesi|Salı|Çarşamba|Perşembe|Cuma|Cumartesi|Pazar)\s+)?(\d{1,2}:\d{2}\s*(?:-|–|to)\s*\d{1,2}:\d{2})",
            re.IGNORECASE,
        )
        room_pattern = re.compile(
            r"\b(BMB[-\s]?\d+|EA[-\s]?\d+|IE[-\s]?\d+|CENG[-\s]?\d+|FZ[-\s]?\d+|MATH[-\s]?\d+|Amfi[-\s]?\d+|Zoom|Online)\b",
            re.IGNORECASE,
        )

        # Scan announcements
        for ann in announcements:
            text = f"{ann.subject}\n{ann.message}"
            has_kw = any(re.search(rf"\b{kw}\b", text, re.IGNORECASE) for kw in keywords)
            if has_kw:
                has_section = any(re.search(sp, text, re.IGNORECASE) for sp in section_patterns)
                if has_section or "all sections" in text.lower() or "tüm gruplar" in text.lower():
                    relevant_announcements.append(ann)

                    # Extract schedule info
                    times = time_pattern.findall(text)
                    rooms = room_pattern.findall(text)
                    day_time_str = " ".join([f"{t[0]}{t[1]}".strip() for t in times]) if times else None
                    room_str = ", ".join(set(rooms)) if rooms else None

                    act_type = "Lab" if "lab" in text.lower() else "Recitation"

                    schedules.append(
                        LabRecitationScheduleEntry(
                            section_matched=f"Section {section}",
                            activity_type=act_type,
                            day_and_time=day_time_str,
                            location_or_room=room_str,
                            raw_context=text[:400],
                            source_url=ann.discussion_url,
                        )
                    )

        # Scan course contents (sections and modules)
        if isinstance(contents, list):
            for sec in contents:
                sec_name = sec.get("name", "")
                sec_summary = clean_html_to_markdown(sec.get("summary"))
                sec_text = f"{sec_name}\n{sec_summary}"

                modules = sec.get("modules", [])
                for mod in modules:
                    m_name = mod.get("name", "")
                    m_desc = clean_html_to_markdown(mod.get("description"))
                    m_url = mod.get("url") or f"{self.base_url}/mod/{mod.get('modname')}/view.php?id={mod.get('id')}"
                    comb_text = f"{m_name}\n{m_desc}"

                    has_kw = any(re.search(rf"\b{kw}\b", comb_text, re.IGNORECASE) for kw in keywords)
                    if has_kw:
                        has_sec = any(re.search(sp, comb_text, re.IGNORECASE) for sp in section_patterns)
                        if has_sec or "schedule" in comb_text.lower() or "çizelge" in comb_text.lower():
                            times = time_pattern.findall(comb_text)
                            rooms = room_pattern.findall(comb_text)
                            day_time_str = " ".join([f"{t[0]}{t[1]}".strip() for t in times]) if times else None
                            room_str = ", ".join(set(rooms)) if rooms else None

                            schedules.append(
                                LabRecitationScheduleEntry(
                                    section_matched=f"Section {section}" if has_sec else "General Schedule",
                                    activity_type="Lab" if "lab" in comb_text.lower() else "Recitation",
                                    day_and_time=day_time_str,
                                    location_or_room=room_str,
                                    raw_context=comb_text[:400],
                                    source_url=m_url,
                                )
                            )

                            # Save related files
                            for item in mod.get("contents", []):
                                related_files.append(
                                    {
                                        "filename": item.get("filename"),
                                        "fileurl": item.get("fileurl"),
                                        "filesize": item.get("filesize"),
                                    }
                                )

        found = len(schedules) > 0 or len(relevant_announcements) > 0

        # Construct summary
        if schedules:
            lines = [f"Found {len(schedules)} lab/recitation entry/entries for Section {section}:"]
            for s in schedules:
                time_info = s.day_and_time or "Time not explicitly specified"
                loc_info = f"at {s.location_or_room}" if s.location_or_room else ""
                lines.append(f"- **{s.activity_type}**: {time_info} {loc_info}")
            summary_msg = "\n".join(lines)
        elif relevant_announcements:
            summary_msg = (
                f"Found {len(relevant_announcements)} announcement(s) regarding lab/recitation for Section {section}."
            )
        else:
            summary_msg = (
                f"No specific lab or recitation schedule found for {course_code} Section {section}. "
                "Please check the general announcements or syllabus."
            )

        return LabRecitationInfo(
            course_code=course_code,
            course_id=course_id,
            course_fullname=course_fullname,
            requested_section=section,
            found=found,
            schedule_summary=summary_msg,
            schedules=schedules,
            relevant_announcements=relevant_announcements,
            related_files_or_links=related_files,
        )
