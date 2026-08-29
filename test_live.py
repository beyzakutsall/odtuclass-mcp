"""
Interactive Live Test Script for METU ODTUClass MCP Server.
Allows selecting any active or past semester (e.g. Spring 2025, Fall 2024, Spring 2024, etc.)
and testing authentication, enrolled courses, announcements, syllabus, and deadlines.
"""

import getpass
import json
import sys
from odtuclass_client import ODTUClassClient, ODTUClassAPIError

SEMESTERS = [
    ("Current / Active Semester (Auto-redirect)", "https://odtuclass.metu.edu.tr"),
    ("2024-2025 Spring (Spring 2025)", "https://odtuclass2025s.metu.edu.tr"),
    ("2024-2025 Fall (Fall 2024)", "https://odtuclass2024f.metu.edu.tr"),
    ("2023-2024 Spring (Spring 2024)", "https://odtuclass2024s.metu.edu.tr"),
    ("2023-2024 Fall (Fall 2023)", "https://odtuclass2023f.metu.edu.tr"),
    ("2023-2024 Summer (Summer 2024)", "https://odtuclass2024sum.metu.edu.tr"),
]


def select_semester() -> str:
    print("\n--- Select Semester / ODTUClass Instance ---")
    for idx, (label, url) in enumerate(SEMESTERS, start=1):
        print(f"  {idx}. {label} [{url}]")
    print(f"  {len(SEMESTERS) + 1}. Custom URL (enter manually)")

    choice_str = input(f"\nSelect semester (1-{len(SEMESTERS) + 1}) [default: 2 (Spring 2025)]: ").strip()
    if not choice_str:
        return SEMESTERS[1][1]

    try:
        choice_idx = int(choice_str)
        if 1 <= choice_idx <= len(SEMESTERS):
            return SEMESTERS[choice_idx - 1][1]
        elif choice_idx == len(SEMESTERS) + 1:
            custom = input("Enter custom ODTUClass URL (e.g. https://odtuclass2025s.metu.edu.tr): ").strip()
            return custom or "https://odtuclass.metu.edu.tr"
    except ValueError:
        pass

    return SEMESTERS[1][1]


def main():
    print("=" * 65)
    print("      METU ODTUClass MCP Server - Live Multi-Semester Test")
    print("=" * 65)

    base_url = select_semester()
    print(f"[*] Target ODTUClass URL: {base_url}")
    client = ODTUClassClient(base_url=base_url)

    print("\n--- Authentication Method ---")
    print("  1. Login with METU Username & Password (Recommended)")
    print("  2. Enter Security Key / Token manually")

    auth_choice = input("\nEnter choice (1 or 2) [default: 1]: ").strip() or "1"
    token = None

    if auth_choice == "1":
        username = input("\nEnter METU Username (e.g. e123456): ").strip()
        password = getpass.getpass("Enter METU Password: ").strip()
        print(f"\n[*] Authenticating with {client.base_url}...")
        try:
            token = client.login_with_credentials(username=username, password=password)
            print(f"[✓] Login successful! Acquired Token: {token[:6]}...{token[-6:]}")
        except ODTUClassAPIError as e:
            print(f"[✗] Login failed: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"[✗] Unexpected error: {e}")
            sys.exit(1)
    else:
        token = input("\nEnter your 32-character ODTUClass Token for this semester: ").strip()
        if not token:
            print("[✗] Token cannot be empty.")
            sys.exit(1)

    # 1. Fetch Enrolled Courses
    print("\n" + "=" * 65)
    print(f"[*] Fetching Enrolled Courses from {client.base_url}...")
    courses = []
    try:
        courses = client.get_enrolled_courses(token)
        print(f"[✓] Found {len(courses)} enrolled course(s):")
        for idx, c in enumerate(courses, start=1):
            print(f"  {idx}. [{c.id}] {c.shortname} - {c.fullname}")
            print(f"     URL: {c.course_url}")
    except Exception as e:
        print(f"[✗] Error fetching courses: {e}")

    # 2. Fetch Upcoming Deadlines / Assignments
    print("\n" + "=" * 65)
    print("[*] Fetching Deadlines & Upcoming Assignments...")
    try:
        assignments = client.get_upcoming_assignments(token)
        if assignments:
            print(f"[✓] Found {len(assignments)} assignment/deadline entry/entries:")
            for a in assignments:
                tag = "[OVERDUE]" if a.is_overdue else "[ACTIVE]"
                print(f"  - {tag} {a.name} ({a.course_name})")
                print(f"    Due Date : {a.due_date_formatted} ({a.time_remaining})")
                if a.action_url:
                    print(f"    Link     : {a.action_url}")
        else:
            print("[✓] No active/upcoming deadlines found in calendar for this semester.")
    except Exception as e:
        print(f"[✗] Error fetching assignments: {e}")

    # 3. Interactive Course Exploration (Announcements & Syllabus)
    if courses:
        print("\n" + "=" * 65)
        print("[*] Deep Dive: Inspect a specific course")
        c_choice = input(f"Select course number to inspect (1-{len(courses)}) or press Enter to skip: ").strip()
        if c_choice.isdigit() and 1 <= int(c_choice) <= len(courses):
            selected_course = courses[int(c_choice) - 1]
            print(f"\n---> Inspecting: {selected_course.shortname} (ID: {selected_course.id})")

            # Announcements
            print("\n[*] Latest Announcements:")
            try:
                announcements = client.get_course_announcements(selected_course.id, token, limit=3)
                if announcements:
                    for ann in announcements:
                        print(f"  • {ann.subject} (by {ann.author_name} on {ann.created_at})")
                        print(f"    {ann.message[:180]}...")
                        if ann.attachments:
                            print(f"    Attachments: {[att.filename for att in ann.attachments]}")
                else:
                    print("  (No announcements found in forum)")
            except Exception as e:
                print(f"  [✗] Error fetching announcements: {e}")

            # Syllabus
            print("\n[*] Syllabus & Course Policy:")
            try:
                syllabus = client.get_course_syllabus(selected_course.id, token)
                if syllabus.syllabus_found:
                    print(f"  [✓] {syllabus.message}")
                    for item in syllabus.items:
                        print(f"  • [{item.type}] {item.title}")
                        if item.file_name:
                            print(f"    File: {item.file_name}")
                        if item.direct_url:
                            print(f"    Link: {item.direct_url}")
                else:
                    print("  (No syllabus resources identified on homepage)")
            except Exception as e:
                print(f"  [✗] Error fetching syllabus: {e}")

    print("\n" + "=" * 65)
    print("  Live test completed successfully!")
    print("=" * 65)


if __name__ == "__main__":
    main()
