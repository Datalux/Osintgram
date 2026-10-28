"""Profile Snapshot & Diff Tracker for Osintgram.

Provides persistent SQLite storage for historical target profile states,
calculates fine-grained structural and metric diffs (including unfollowers,
bio link changes, and avatar hashes), and formats human-readable summaries.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_DB_PATH = Path("cache/snapshots.sqlite3")


def get_db_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Initialize and return an SQLite connection with WAL enabled."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if isinstance(db_path, str) and db_path != ":memory:":
        db_path = Path(db_path)
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if str(db_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    """Create schema tables and indexes if they do not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            username TEXT NOT NULL,
            full_name TEXT,
            biography TEXT,
            external_url TEXT,
            profile_pic_url TEXT,
            avatar_hash TEXT,
            follower_count INTEGER DEFAULT 0,
            following_count INTEGER DEFAULT 0,
            media_count INTEGER DEFAULT 0,
            is_private INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            is_business INTEGER DEFAULT 0,
            category TEXT,
            public_email TEXT,
            contact_phone_number TEXT,
            bio_links TEXT,
            followers_sample TEXT,
            followings_sample TEXT,
            raw_data TEXT
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshots_target_timestamp 
        ON profile_snapshots (target, timestamp DESC);
    """)
    conn.commit()


def compute_avatar_hash(url_or_content: Optional[str]) -> str:
    """Generate SHA-256 fingerprint for profile picture URL or bytes."""
    if not url_or_content:
        return ""
    return hashlib.sha256(url_or_content.strip().encode("utf-8")).hexdigest()[:16]


def create_snapshot(
    target: str,
    profile_data: Dict[str, Any],
    followers: Optional[List[Dict[str, Any]]] = None,
    followings: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Capture and record a new profile snapshot in the database."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    target_clean = target.strip().lstrip("@").lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    avatar_url = profile_data.get("profile_pic_url") or profile_data.get("avatar_url") or ""
    avatar_hash = compute_avatar_hash(avatar_url)

    # Extract bio links list if present
    bio_links = profile_data.get("bio_links") or []
    if isinstance(bio_links, list):
        bio_links_clean = [
            link.get("url", link) if isinstance(link, dict) else str(link)
            for link in bio_links
        ]
    else:
        bio_links_clean = []

    # Extract sample usernames for network differential tracking
    def _extract_usernames(user_list: Optional[List[Dict[str, Any]]]) -> List[str]:
        if not user_list:
            return []
        res = []
        for u in user_list:
            if isinstance(u, dict) and "username" in u:
                res.append(u["username"].lower())
            elif isinstance(u, str):
                res.append(u.lower())
        return sorted(list(set(res)))

    followers_sample = _extract_usernames(followers)
    followings_sample = _extract_usernames(followings)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO profile_snapshots (
                target, timestamp, username, full_name, biography, external_url,
                profile_pic_url, avatar_hash, follower_count, following_count,
                media_count, is_private, is_verified, is_business, category,
                public_email, contact_phone_number, bio_links, followers_sample,
                followings_sample, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            target_clean,
            now_iso,
            profile_data.get("username") or target_clean,
            profile_data.get("full_name") or "",
            profile_data.get("biography") or "",
            profile_data.get("external_url") or "",
            avatar_url,
            avatar_hash,
            int(profile_data.get("follower_count") or profile_data.get("followers") or 0),
            int(profile_data.get("following_count") or profile_data.get("following") or 0),
            int(profile_data.get("media_count") or profile_data.get("posts") or 0),
            1 if profile_data.get("is_private") else 0,
            1 if profile_data.get("is_verified") else 0,
            1 if profile_data.get("is_business") else 0,
            profile_data.get("category") or "",
            profile_data.get("public_email") or "",
            profile_data.get("contact_phone_number") or "",
            json.dumps(bio_links_clean),
            json.dumps(followers_sample),
            json.dumps(followings_sample),
            json.dumps(profile_data, ensure_ascii=False),
        ))
        snapshot_id = cursor.lastrowid
        conn.commit()

    return {
        "id": snapshot_id,
        "target": target_clean,
        "timestamp": now_iso,
        "username": profile_data.get("username") or target_clean,
        "full_name": profile_data.get("full_name") or "",
        "follower_count": int(profile_data.get("follower_count") or profile_data.get("followers") or 0),
        "following_count": int(profile_data.get("following_count") or profile_data.get("following") or 0),
        "media_count": int(profile_data.get("media_count") or profile_data.get("posts") or 0),
        "avatar_hash": avatar_hash,
    }


def list_snapshots(
    target: str,
    limit: int = 50,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve list of saved snapshots for a target ordered by timestamp descending."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    target_clean = target.strip().lstrip("@").lower()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, target, timestamp, username, full_name, follower_count,
                   following_count, media_count, is_private, is_verified, avatar_hash
            FROM profile_snapshots
            WHERE target = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (target_clean, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_snapshot(
    snapshot_id: int,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch complete snapshot by ID."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profile_snapshots WHERE id = ?", (snapshot_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        for json_col in ("bio_links", "followers_sample", "followings_sample", "raw_data"):
            if res.get(json_col):
                try:
                    res[json_col] = json.loads(res[json_col])
                except Exception:
                    pass
        return res


def compare_snapshots(old_snap: Dict[str, Any], new_snap: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two snapshots and calculate structural, metric, and network deltas."""
    target = new_snap.get("target") or old_snap.get("target") or ""
    old_time = old_snap.get("timestamp", "")
    new_time = new_snap.get("timestamp", "")

    field_changes: Dict[str, Dict[str, Any]] = {}
    tracked_fields = [
        ("username", "Username"),
        ("full_name", "Full Name"),
        ("biography", "Bio"),
        ("external_url", "Bio Link"),
        ("category", "Category"),
        ("public_email", "Email"),
        ("contact_phone_number", "Phone"),
        ("is_private", "Private Status"),
        ("is_verified", "Verified Badge"),
        ("avatar_hash", "Profile Picture"),
    ]

    for key, label in tracked_fields:
        old_val = old_snap.get(key)
        new_val = new_snap.get(key)
        if old_val != new_val:
            field_changes[key] = {
                "label": label,
                "old": old_val,
                "new": new_val,
            }

    # Bio links set diff
    old_links = set(old_snap.get("bio_links") or [])
    new_links = set(new_snap.get("bio_links") or [])
    added_links = sorted(list(new_links - old_links))
    removed_links = sorted(list(old_links - new_links))

    # Metric changes
    old_followers = int(old_snap.get("follower_count") or 0)
    new_followers = int(new_snap.get("follower_count") or 0)
    diff_followers = new_followers - old_followers
    growth_pct = round((diff_followers / old_followers * 100), 2) if old_followers > 0 else 0.0

    old_followings = int(old_snap.get("following_count") or 0)
    new_followings = int(new_snap.get("following_count") or 0)
    diff_followings = new_followings - old_followings

    old_posts = int(old_snap.get("media_count") or 0)
    new_posts = int(new_snap.get("media_count") or 0)
    diff_posts = new_posts - old_posts

    # Network followers/following diffs (if samples were tracked)
    old_fol_set = set(old_snap.get("followers_sample") or [])
    new_fol_set = set(new_snap.get("followers_sample") or [])
    new_followers_list = sorted(list(new_fol_set - old_fol_set))
    lost_followers_list = sorted(list(old_fol_set - new_fol_set))

    old_fing_set = set(old_snap.get("followings_sample") or [])
    new_fing_set = set(new_snap.get("followings_sample") or [])
    new_followings_list = sorted(list(new_fing_set - old_fing_set))
    unfollowed_list = sorted(list(old_fing_set - new_fing_set))

    has_changes = bool(
        field_changes
        or added_links
        or removed_links
        or diff_followers != 0
        or diff_followings != 0
        or diff_posts != 0
        or new_followers_list
        or lost_followers_list
        or new_followings_list
        or unfollowed_list
    )

    # Generate human-readable summary bullet list
    summary_lines = []
    if diff_followers != 0:
        sym = "+" if diff_followers > 0 else ""
        summary_lines.append(f"Followers: {old_followers:,} → {new_followers:,} ({sym}{diff_followers:,}, {growth_pct:+0.1f}%)")
    if diff_followings != 0:
        sym = "+" if diff_followings > 0 else ""
        summary_lines.append(f"Following: {old_followings:,} → {new_followings:,} ({sym}{diff_followings:,})")
    if diff_posts != 0:
        sym = "+" if diff_posts > 0 else ""
        summary_lines.append(f"Posts: {old_posts:,} → {new_posts:,} ({sym}{diff_posts:,})")

    for k, change in field_changes.items():
        if k == "avatar_hash":
            summary_lines.append("Profile picture was updated (new avatar image)")
        elif k in ("is_private", "is_verified"):
            was = "enabled" if change["old"] else "disabled"
            now = "enabled" if change["new"] else "disabled"
            summary_lines.append(f"{change['label']} changed from {was} to {now}")
        else:
            summary_lines.append(f"{change['label']} changed: '{change['old']}' → '{change['new']}'")

    if added_links:
        summary_lines.append(f"Added bio links: {', '.join(added_links)}")
    if removed_links:
        summary_lines.append(f"Removed bio links: {', '.join(removed_links)}")
    if new_followers_list:
        summary_lines.append(f"Detected new followers ({len(new_followers_list)}): @{', @'.join(new_followers_list[:5])}")
    if lost_followers_list:
        summary_lines.append(f"Detected unfollowers ({len(lost_followers_list)}): @{', @'.join(lost_followers_list[:5])}")
    if new_followings_list:
        summary_lines.append(f"Target started following ({len(new_followings_list)}): @{', @'.join(new_followings_list[:5])}")
    if unfollowed_list:
        summary_lines.append(f"Target unfollowed ({len(unfollowed_list)}): @{', @'.join(unfollowed_list[:5])}")

    return {
        "target": target,
        "old_snapshot_id": old_snap.get("id"),
        "new_snapshot_id": new_snap.get("id"),
        "old_timestamp": old_time,
        "new_timestamp": new_time,
        "has_changes": has_changes,
        "field_changes": field_changes,
        "metric_deltas": {
            "followers": {"old": old_followers, "new": new_followers, "diff": diff_followers, "growth_percent": growth_pct},
            "following": {"old": old_followings, "new": new_followings, "diff": diff_followings},
            "posts": {"old": old_posts, "new": new_posts, "diff": diff_posts},
        },
        "link_changes": {
            "added": added_links,
            "removed": removed_links,
        },
        "network_changes": {
            "new_followers": new_followers_list,
            "lost_followers": lost_followers_list,
            "new_followings": new_followings_list,
            "unfollowed": unfollowed_list,
        },
        "summary": summary_lines,
    }


def diff_latest_two(
    target: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Compare the most recent snapshot against the second most recent for target."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    snaps = list_snapshots(target, limit=2, db_path=db_path)
    if len(snaps) < 2:
        return None
    latest = get_snapshot(snaps[0]["id"], db_path=db_path)
    previous = get_snapshot(snaps[1]["id"], db_path=db_path)
    if not latest or not previous:
        return None
    return compare_snapshots(previous, latest)
