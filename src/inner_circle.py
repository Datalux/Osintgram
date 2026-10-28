"""Inner Circle Algorithm for Instagram OSINT.

Calculates affinity and closeness scores between the target profile and
interacting accounts based on weighted multi-signal heuristics:
- Mutual follows (target follows user AND user follows target)
- In-photo usertags on target's posts
- Comment frequency & recency on target's posts
- Mentions in captions (@username)
"""
import re
from typing import Any, Dict, List, Optional

WEIGHT_MUTUAL_FOLLOW = 3.5
WEIGHT_TAGGED_POST = 3.0
WEIGHT_COMMENT = 1.5
WEIGHT_CAPTION_MENTION = 2.0


class InnerCircleAnalyzer:
    """Ranks and categorizes target profile's closest social circle."""

    def __init__(self, target_username: str):
        self.target = (target_username or "").strip().lower()

    def analyze(
        self,
        posts: List[Dict[str, Any]],
        comments_by_post: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        followers: Optional[List[Dict[str, Any]]] = None,
        following: Optional[List[Dict[str, Any]]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Compute ranked affinity scores for interacting users."""
        comments_by_post = comments_by_post or {}
        followers = followers or []
        following = following or []

        # 1. Resolve mutual followers
        followers_map = {
            (u.get("username") or "").lower(): u
            for u in followers
            if u.get("username")
        }
        following_map = {
            (u.get("username") or "").lower(): u
            for u in following
            if u.get("username")
        }
        mutual_usernames = (
            set(followers_map.keys()) & set(following_map.keys())
        )

        # Interaction tracker by username
        users: Dict[str, Dict[str, Any]] = {}

        def get_or_create(
            username: str, meta: Optional[Dict[str, Any]] = None
        ):
            uname_clean = username.strip().lower()
            if uname_clean == self.target or not uname_clean:
                return None
            if uname_clean not in users:
                user_info = (
                    meta
                    or followers_map.get(uname_clean)
                    or following_map.get(uname_clean)
                    or {}
                )
                users[uname_clean] = {
                    "username": uname_clean,
                    "id": user_info.get("id") or user_info.get("pk"),
                    "full_name": user_info.get("full_name") or "",
                    "profile_pic_url": user_info.get("profile_pic_url") or "",
                    "score": 0.0,
                    "is_mutual": uname_clean in mutual_usernames,
                    "is_following_target": uname_clean in followers_map,
                    "is_followed_by_target": uname_clean in following_map,
                    "tagged_count": 0,
                    "comments_count": 0,
                    "mentions_count": 0,
                    "interactions": [],
                }
            return users[uname_clean]

        # Seed mutual followers
        for uname in mutual_usernames:
            rec = get_or_create(uname)
            if rec:
                rec["score"] += WEIGHT_MUTUAL_FOLLOW
                rec["interactions"].append({
                    "type": "mutual_follow",
                    "weight": WEIGHT_MUTUAL_FOLLOW,
                    "description": "Mutual connection (follows each other)",
                })

        # 2. Analyze posts (usertags and caption mentions)
        for post in posts:
            post_id = str(post.get("id") or post.get("pk") or "")

            # Usertags (tagged in photo/video)
            usertags = post.get("usertags") or []
            if isinstance(usertags, dict):
                usertags = usertags.get("in") or []
            for tag in usertags:
                u_obj = tag.get("user") or {}
                uname = u_obj.get("username")
                if not uname:
                    continue
                rec = get_or_create(uname, meta=u_obj)
                if rec:
                    rec["score"] += WEIGHT_TAGGED_POST
                    rec["tagged_count"] += 1
                    rec["interactions"].append({
                        "type": "tagged_photo",
                        "post_id": post_id,
                        "weight": WEIGHT_TAGGED_POST,
                        "description": "Tagged in target photo/media",
                    })

            # Caption mentions (@username)
            caption_raw = post.get("caption")
            if isinstance(caption_raw, dict):
                caption_text = caption_raw.get("text") or ""
            else:
                caption_text = str(caption_raw or "")
            if caption_text:
                for mention in re.findall(r"@([A-Za-z0-9_.]+)", caption_text):
                    m_clean = mention.strip().lower()
                    rec = get_or_create(m_clean)
                    if rec:
                        rec["score"] += WEIGHT_CAPTION_MENTION
                        rec["mentions_count"] += 1
                        rec["interactions"].append({
                            "type": "caption_mention",
                            "post_id": post_id,
                            "weight": WEIGHT_CAPTION_MENTION,
                            "description": (
                                f"Mentioned in caption: @{m_clean}"
                            ),
                        })

            # Comments on this post
            post_comments = comments_by_post.get(post_id) or []
            for comment in post_comments:
                c_user = comment.get("user") or {}
                c_uname = c_user.get("username")
                if not c_uname:
                    continue
                rec = get_or_create(c_uname, meta=c_user)
                if rec:
                    rec["score"] += WEIGHT_COMMENT
                    rec["comments_count"] += 1
                    rec["interactions"].append({
                        "type": "comment",
                        "post_id": post_id,
                        "text": (comment.get("text") or "")[:80],
                        "weight": WEIGHT_COMMENT,
                        "description": "Left comment on target post",
                    })

        # 3. Classify tier & rank
        results = []
        for u in users.values():
            score = round(u["score"], 1)
            u["score"] = score
            if score >= 8.0:
                tier = "Core Confidant"
            elif score >= 4.0:
                tier = "Close Friend"
            else:
                tier = "Frequent Contact"
            u["tier"] = tier
            results.append(u)

        results.sort(
            key=lambda x: (x["score"], x["tagged_count"], x["comments_count"]),
            reverse=True,
        )
        return results[:limit]
