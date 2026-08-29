"""
ODTUClass MCP Server Data Models.
Defines Pydantic models and type definitions for courses, announcements,
syllabus items, upcoming assignments, and lab/recitation information.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CourseInfo(BaseModel):
    """Information about an enrolled course on ODTUClass."""
    id: int = Field(..., description="Unique course identifier in ODTUClass Moodle")
    shortname: str = Field(..., description="Course short name/code (e.g., CENG140.1, MATH119)")
    fullname: str = Field(..., description="Full course title (e.g., CENG140 C Programming Section 1)")
    idnumber: Optional[str] = Field(None, description="Course ID number if set")
    summary: Optional[str] = Field(None, description="Course description/summary text")
    course_url: str = Field(..., description="Direct web URL to course homepage")
    startdate: Optional[int] = Field(None, description="Course start timestamp")
    enddate: Optional[int] = Field(None, description="Course end timestamp")
    enrolled_student_count: Optional[int] = Field(None, description="Number of enrolled students if available")


class AnnouncementAttachment(BaseModel):
    """Attachment file in a forum announcement."""
    filename: str = Field(..., description="File name of the attachment")
    fileurl: str = Field(..., description="URL to download or view the attachment")
    filesize: Optional[int] = Field(None, description="File size in bytes")
    mimetype: Optional[str] = Field(None, description="MIME type of the attachment")


class AnnouncementItem(BaseModel):
    """A single announcement/forum discussion post from a course."""
    id: int = Field(..., description="Post or discussion ID")
    discussion_id: int = Field(..., description="Discussion thread ID")
    subject: str = Field(..., description="Announcement subject/title")
    author_name: str = Field(..., description="Name of the instructor/TA who posted")
    created_at: str = Field(..., description="Creation date formatted in ISO/human-readable string")
    modified_at: Optional[str] = Field(None, description="Last modification date")
    message: str = Field(..., description="Clean text/markdown content of the announcement")
    attachments: List[AnnouncementAttachment] = Field(default_factory=list, description="List of attached files")
    discussion_url: str = Field(..., description="Direct link to discussion thread on ODTUClass")


class SyllabusItem(BaseModel):
    """Identified course syllabus resource or section."""
    course_id: int = Field(..., description="ODTUClass Course ID")
    title: str = Field(..., description="Resource or Section Title")
    type: str = Field(..., description="Type of syllabus item: 'file_resource', 'url_link', 'page_content', or 'section_overview'")
    file_name: Optional[str] = Field(None, description="File name if syllabus is a downloadable file (e.g., syllabus.pdf)")
    file_url: Optional[str] = Field(None, description="Download/view URL for file or resource")
    content_summary: Optional[str] = Field(None, description="Extracted text summary or content preview")
    direct_url: Optional[str] = Field(None, description="Direct web URL on ODTUClass")


class SyllabusResponse(BaseModel):
    """Result returned for a course syllabus query."""
    course_id: int
    course_name: Optional[str] = None
    syllabus_found: bool
    items: List[SyllabusItem] = Field(default_factory=list)
    message: str = Field(..., description="Summary message or status")


class UpcomingAssignment(BaseModel):
    """An upcoming assignment, quiz, or event with deadline."""
    id: int = Field(..., description="Event or Assignment ID")
    name: str = Field(..., description="Title of the assignment or deadline event")
    course_id: int = Field(..., description="Associated Course ID")
    course_name: str = Field(..., description="Course short name or full name")
    event_type: str = Field(..., description="Type of event: 'assign', 'quiz', 'due', 'calendar'")
    due_timestamp: int = Field(..., description="Unix timestamp of due date")
    due_date_formatted: str = Field(..., description="Human-readable due date & time")
    time_remaining: str = Field(..., description="Time left until deadline (e.g. '2 days, 4 hours left')")
    is_overdue: bool = Field(False, description="Whether deadline has passed")
    action_url: Optional[str] = Field(None, description="Direct URL to submit or view activity")
    description: Optional[str] = Field(None, description="Clean description/instructions if available")


class LabRecitationScheduleEntry(BaseModel):
    """Detected schedule time, room, or group information for lab/recitation."""
    section_matched: Optional[str] = Field(None, description="Matched section or group keyword (e.g. 'Section 1')")
    activity_type: str = Field(..., description="Type of session: 'Lab', 'Recitation', 'PS', 'Workshop'")
    day_and_time: Optional[str] = Field(None, description="Detected day and time slot (e.g., 'Monday 13:40 - 15:30')")
    location_or_room: Optional[str] = Field(None, description="Lab room or classroom (e.g. 'BMB-1', 'Online Zoom')")
    assistant_or_instructor: Optional[str] = Field(None, description="Name of teaching assistant if mentioned")
    raw_context: str = Field(..., description="Excerpt from course page or announcement containing this info")
    source_url: Optional[str] = Field(None, description="Direct link where this info was found")


class LabRecitationInfo(BaseModel):
    """Complete lab and recitation information for a specific course and section."""
    course_code: str
    course_id: Optional[int] = None
    course_fullname: Optional[str] = None
    requested_section: int
    found: bool
    schedule_summary: str = Field(..., description="Human-friendly summary of lab/recitation schedule")
    schedules: List[LabRecitationScheduleEntry] = Field(default_factory=list)
    relevant_announcements: List[AnnouncementItem] = Field(default_factory=list)
    related_files_or_links: List[Dict[str, Any]] = Field(default_factory=list)
