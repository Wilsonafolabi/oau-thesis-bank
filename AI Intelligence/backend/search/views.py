import re

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.contrib.postgres.search import SearchVector
from django.db.models import Case, F, IntegerField, Q, Value, When
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from theses.models import Thesis
from theses.serializers import ThesisListSerializer


class SearchView(generics.ListAPIView):
    """Full-text search of published public theses with optional filters."""

    serializer_class = ThesisListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        public_theses = Q(status=Thesis.Status.PUBLISHED, access_policy=Thesis.AccessPolicy.PUBLIC)
        user = self.request.user
        if user.is_authenticated and user.role == "admin":
            qs = Thesis.objects.all()
        elif user.is_authenticated:
            qs = Thesis.objects.filter(public_theses | Q(owner=user))
        else:
            qs = Thesis.objects.filter(public_theses)
        qs = qs.select_related("owner").prefetch_related("tags")

        params = self.request.query_params
        filters = {
            "department": "department__iexact",
            "faculty": "faculty__iexact",
            "year": "year",
            "tag": "tags__name__iexact",
        }
        for param, lookup in filters.items():
            value = params.get(param)
            if value:
                qs = qs.filter(**{lookup: value})

        return qs.distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        raw_query = (request.query_params.get("q") or "").strip()
        if request.query_params.get("scope") == "title" and raw_query:
            return self.search_titles(queryset, raw_query)

        if not raw_query:
            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "count": len(serializer.data),
                    "results": [{"thesis": item, "matched_concepts": [], "relevance_score": None} for item in serializer.data],
                }
            )

        query = SearchQuery(raw_query, config="english")
        # Rank weights (ordered D, C, B, A): abstract+tags D, supervisor C, author B, title A.
        rank_weights = [0.1, 0.3, 0.6, 1.0]
        ranked = list(
            queryset.annotate(rank=SearchRank(F("search_vector"), query, weights=rank_weights))
            .filter(search_vector=query)
            .order_by("-rank")
        )
        max_rank = ranked[0].rank if ranked else 0

        terms = raw_query.lower().split()
        results = []
        for thesis in ranked:
            match_fields = {
                "title": thesis.title,
                "author": thesis.author,
                "supervisor": thesis.supervisor,
                "abstract": thesis.abstract,
                "tags": " ".join(tag.name for tag in thesis.tags.all()),
                "department": thesis.department,
                "faculty": thesis.faculty,
            }
            matched = sorted(
                {term for term in terms if any(term in field.lower() for field in match_fields.values())}
            )
            raw_rank = float(getattr(thesis, "rank", 0.0))
            relevance_score = round(raw_rank / max_rank, 4) if max_rank else 1.0
            results.append(
                {
                    "thesis": self.get_serializer(thesis).data,
                    "matched_concepts": matched,
                    "relevance_score": relevance_score,
                }
            )

        return Response({"count": len(results), "results": results})

    def search_titles(self, queryset, raw_query):
        """Rank public thesis records by title, similar to scholarly search."""
        raw_query = " ".join(raw_query.split())[:250]
        terms = sorted(set(re.findall(r"[\w]+", raw_query.lower())))
        query = SearchQuery(raw_query, config="english", search_type="plain")

        # Require every meaningful word for the fallback, while allowing full
        # text search to match English inflections (e.g. "analyses"/"analysis").
        all_terms = Q()
        for term in terms:
            all_terms &= Q(title__icontains=term)

        candidates = (
            queryset.annotate(
                title_rank=SearchRank(SearchVector("title", config="english"), query),
                exact_title=Case(
                    When(title__iexact=raw_query, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                phrase_title=Case(
                    When(title__icontains=raw_query, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .filter(
                Q(title_rank__gt=0)
                | Q(title__icontains=raw_query)
                | (all_terms if terms else Q(pk__in=[]))
            )
            .order_by("-exact_title", "-phrase_title", "-title_rank", "-year", "-created_at")
        )

        ranked = list(candidates)
        max_rank = max((float(item.title_rank or 0) for item in ranked), default=0)
        results = []
        for thesis in ranked:
            title = thesis.title.lower()
            matched = [term for term in terms if term in title]
            score = (
                1.0
                if thesis.exact_title
                else 0.95
                if thesis.phrase_title
                else round(0.5 + 0.45 * float(thesis.title_rank or 0) / max_rank, 4)
                if max_rank
                else 0.5
            )
            results.append(
                {
                    "thesis": self.get_serializer(thesis).data,
                    "matched_concepts": matched,
                    "relevance_score": score,
                }
            )

        return Response({"count": len(results), "results": results})
