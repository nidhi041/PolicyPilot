"""HR Analytics API for question volume, topics, outcomes, feedback, and policy clarity gaps."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import inspect
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import AuthenticatedUser, require_hr_admin
from app.db.models import Conversation, Message, MessageFeedback, Policy, Profile
from app.errors import AppError
from app.policies import get_db_session

async def _maybe_await(val: Any) -> Any:
    return await val if inspect.isawaitable(val) else val

class DailyTrendItem(BaseModel):
    date: str; questions_count: int

class QuestionVolume(BaseModel):
    total_questions: int = 0; total_conversations: int = 0
    daily_trend: list[DailyTrendItem] = Field(default_factory=list)

class AnswerOutcomes(BaseModel):
    total_answers: int = 0; grounded_answers_count: int = 0; abstention_count: int = 0
    grounded_rate: float = 0.0; abstention_rate: float = 0.0
    confirmed_resolved_count: int = 0; confirmed_unresolved_count: int = 0

class FeedbackSummary(BaseModel):
    total_feedback_count: int = 0; positive_feedback_count: int = 0; negative_feedback_count: int = 0
    satisfaction_rate: float = 0.0; response_rate: float = 0.0

class TopicMetric(BaseModel):
    category: str; count: int; percentage: float

class UnansweredQuestionItem(BaseModel):
    question: str; count: int; last_asked: str; outcome: str = "abstention"

class AnalyticsFilterSummary(BaseModel):
    region: Optional[str] = None; start_date: Optional[str] = None; end_date: Optional[str] = None

class HRAnalyticsOverview(BaseModel):
    filters: AnalyticsFilterSummary
    question_volume: QuestionVolume
    answer_outcomes: AnswerOutcomes
    feedback_summary: FeedbackSummary
    popular_topics: list[TopicMetric] = Field(default_factory=list)
    unanswered_questions: list[UnansweredQuestionItem] = Field(default_factory=list)

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])

def _parse_query_date(val: Optional[str]) -> Optional[datetime]:
    if not val or not val.strip(): return None
    clean = val.strip().replace(" ", "+")
    try:
        if clean.endswith("Z"): clean = clean[:-1] + "+00:00"
        dt = datetime.fromisoformat(clean)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise AppError(f"Invalid date format: '{val}'. Expected ISO format.", 400, "INVALID_DATE_FORMAT")

@analytics_router.get("/overview", response_model=HRAnalyticsOverview)
async def get_analytics_overview(
    region: Optional[str] = Query(None, description="Filter by authorized region"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    current_user: AuthenticatedUser = Depends(require_hr_admin),
    session: AsyncSession = Depends(get_db_session),
) -> HRAnalyticsOverview:
    start_dt, end_dt = _parse_query_date(start_date), _parse_query_date(end_date)
    if start_dt and end_dt and end_dt < start_dt:
        raise AppError("end_date cannot be earlier than start_date", 400, "INVALID_DATE_RANGE")

    hr_region = current_user.profile.region.upper() if current_user.profile.region else "GLOBAL"
    req_region = region.strip().upper() if region and region.strip() else None
    if hr_region != "GLOBAL":
        if req_region and req_region not in (hr_region, "GLOBAL"):
            raise AppError(f"Forbidden: Region filter '{req_region}' exceeds authorized region '{hr_region}'", 403, "FORBIDDEN")
        effective_region = hr_region
    else:
        effective_region = req_region if req_region and req_region != "ALL" else None

    conv_stmt = select(Conversation.id).join(Profile, Conversation.user_id == Profile.user_id)
    if effective_region: conv_stmt = conv_stmt.where(Profile.region == effective_region)
    conv_ids = [r[0] for r in (await _maybe_await(session.execute(conv_stmt))).all()]

    filter_summary = AnalyticsFilterSummary(
        region=effective_region or "GLOBAL",
        start_date=start_dt.isoformat() if start_dt else None,
        end_date=end_dt.isoformat() if end_dt else None,
    )
    if not conv_ids:
        return HRAnalyticsOverview(filters=filter_summary, question_volume=QuestionVolume(), answer_outcomes=AnswerOutcomes(), feedback_summary=FeedbackSummary(), popular_topics=[], unanswered_questions=[])

    msg_stmt = select(Message).where(Message.conversation_id.in_(conv_ids)).order_by(Message.created_at.asc())
    if start_dt: msg_stmt = msg_stmt.where(Message.created_at >= start_dt)
    if end_dt: msg_stmt = msg_stmt.where(Message.created_at <= end_dt)
    messages = list((await _maybe_await(session.execute(msg_stmt))).scalars().all())

    user_msgs = [m for m in messages if m.role == "user"]
    asst_msgs = [m for m in messages if m.role == "assistant"]
    daily_counts: dict[str, int] = defaultdict(int)
    for m in user_msgs: daily_counts[m.created_at.strftime("%Y-%m-%d")] += 1
    daily_trend = [DailyTrendItem(date=d, questions_count=c) for d, c in sorted(daily_counts.items())]

    total_answers = len(asst_msgs)
    grounded_count = sum(1 for a in asst_msgs if a.is_grounded and a.status == "answered")
    abstention_count = sum(1 for a in asst_msgs if a.status == "abstention")

    asst_ids = [a.id for a in asst_msgs]
    feedbacks = list((await _maybe_await(session.execute(select(MessageFeedback).where(MessageFeedback.message_id.in_(asst_ids))))).scalars().all()) if asst_ids else []
    pos_fb = sum(1 for f in feedbacks if f.rating == "up")
    neg_fb = sum(1 for f in feedbacks if f.rating == "down")
    tot_fb = len(feedbacks)

    pol_rows = list((await _maybe_await(session.execute(select(Policy.title, Policy.category)))).all())
    cat_map = {title.strip().lower(): cat.strip() for title, cat in pol_rows if cat}
    topic_counts: dict[str, int] = defaultdict(int)
    for a in asst_msgs:
        for cit in (a.citations or []):
            pt = (cit.get("policy_title") or "").strip().lower()
            topic_counts[cat_map.get(pt, "General")] += 1

    tot_topics = sum(topic_counts.values())
    popular_topics = [
        TopicMetric(category=c, count=n, percentage=round((n / tot_topics) * 100, 1) if tot_topics > 0 else 0.0)
        for c, n in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    conv_user_msgs: dict[uuid.UUID, list[Message]] = defaultdict(list)
    for m in user_msgs: conv_user_msgs[m.conversation_id].append(m)
    unanswered_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "last_asked": "", "outcome": "abstention"})
    neg_fb_msg_ids = {f.message_id for f in feedbacks if f.rating == "down"}

    for a in asst_msgs:
        if a.status == "abstention" or a.id in neg_fb_msg_ids:
            u_candidates = [u for u in conv_user_msgs[a.conversation_id] if u.created_at <= a.created_at]
            if u_candidates:
                q_text = u_candidates[-1].content.strip()
                outcome = "negative_feedback" if a.id in neg_fb_msg_ids and a.status != "abstention" else "abstention"
                unanswered_counts[q_text]["count"] += 1
                unanswered_counts[q_text]["last_asked"] = a.created_at.isoformat()
                unanswered_counts[q_text]["outcome"] = outcome

    return HRAnalyticsOverview(
        filters=filter_summary,
        question_volume=QuestionVolume(total_questions=len(user_msgs), total_conversations=len({m.conversation_id for m in user_msgs}), daily_trend=daily_trend),
        answer_outcomes=AnswerOutcomes(
            total_answers=total_answers, grounded_answers_count=grounded_count, abstention_count=abstention_count,
            grounded_rate=round((grounded_count / total_answers) * 100, 1) if total_answers > 0 else 0.0,
            abstention_rate=round((abstention_count / total_answers) * 100, 1) if total_answers > 0 else 0.0,
            confirmed_resolved_count=pos_fb, confirmed_unresolved_count=abstention_count + neg_fb,
        ),
        feedback_summary=FeedbackSummary(
            total_feedback_count=tot_fb, positive_feedback_count=pos_fb, negative_feedback_count=neg_fb,
            satisfaction_rate=round((pos_fb / tot_fb) * 100, 1) if tot_fb > 0 else 0.0,
            response_rate=round((tot_fb / total_answers) * 100, 1) if total_answers > 0 else 0.0,
        ),
        popular_topics=popular_topics,
        unanswered_questions=[
            UnansweredQuestionItem(question=q, count=info["count"], last_asked=info["last_asked"], outcome=info["outcome"])
            for q, info in sorted(unanswered_counts.items(), key=lambda x: x[1]["count"], reverse=True)
        ],
    )
