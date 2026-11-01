"""URL configuration for the AI Integration app.

All endpoints are Django-mediated proxies to the V2 AI service.
Django authenticates the user, enforces thesis permissions, generates
trace IDs, and forwards to V2 with server-to-service auth.
"""

from django.urls import path

from .views import (
    AIHealthView,
    AIMemoryDetailView,
    AIMemoryListCreateView,
    AIMemoryPreferencesView,
    AIMemoryRetrieveView,
    AIMemoryThesisSummaryView,
    AIDocumentDeleteView,
    AIDocumentUploadView,
    AIAssistantChatView,
    AIJobStatusView,
    AIRAGAskView,
    AIRecommendationView,
    AIResearchGapView,
    AISimilarityCheckView,
    AITopicAnalysisView,
    AIWritingDetectView,
    AIPlagiarismAssessView,
)

urlpatterns = [
    path("health/", AIHealthView.as_view(), name="ai-health"),
    path("documents/upload/", AIDocumentUploadView.as_view(), name="ai-document-upload"),
    path(
        "documents/jobs/<str:job_id>/",
        AIJobStatusView.as_view(),
        name="ai-job-status",
    ),
    path(
        "documents/<str:backend_thesis_id>/",
        AIDocumentDeleteView.as_view(),
        name="ai-document-delete",
    ),
    path("rag/ask/", AIRAGAskView.as_view(), name="ai-rag-ask"),
    path("assistant/chat/", AIAssistantChatView.as_view(), name="ai-assistant-chat"),
    path(
        "research-gaps/ask/",
        AIResearchGapView.as_view(),
        name="ai-research-gap-ask",
    ),
    path(
        "topics/analyze/",
        AITopicAnalysisView.as_view(),
        name="ai-topic-analysis",
    ),
    path(
        "recommendations/",
        AIRecommendationView.as_view(),
        name="ai-recommendations",
    ),
    path(
        "similarity/check/",
        AISimilarityCheckView.as_view(),
        name="ai-similarity-check",
    ),
    path(
        "plagiarism/assess/",
        AIPlagiarismAssessView.as_view(),
        name="ai-plagiarism-assess",
    ),
    path(
        "ai-writing/detect/",
        AIWritingDetectView.as_view(),
        name="ai-writing-detect",
    ),

    # Static memory routes MUST precede the dynamic memory/<memory_id>/ route,
    # otherwise "retrieve", "thesis-summaries" and "preferences" are captured
    # as memory_id values and resolve to the detail view.
    path("memory/retrieve/", AIMemoryRetrieveView.as_view(), name="ai-memory-retrieve"),
    path(
        "memory/thesis-summaries/",
        AIMemoryThesisSummaryView.as_view(),
        name="ai-memory-thesis-summary",
    ),
    path(
        "memory/thesis-summaries/<str:backend_thesis_id>/",
        AIMemoryThesisSummaryView.as_view(),
        name="ai-memory-thesis-summary-detail",
    ),
    path(
        "memory/preferences/",
        AIMemoryPreferencesView.as_view(),
        name="ai-memory-preferences",
    ),

    # GET (list) and POST (create) share one URL; the previous duplicate path
    # meant POST was swallowed by the list view and returned 405.
    path("memory/", AIMemoryListCreateView.as_view(), name="ai-memory-root"),
    path("memory/<str:memory_id>/", AIMemoryDetailView.as_view(), name="ai-memory-detail"),
]
