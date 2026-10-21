import coreapi
import coreschema
import django_filters
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

from core.models import Board, Pin
from core.serializers import filter_private_board


class PinFilter(django_filters.FilterSet):
    """
    `pins__id` is the board id (`Board.pins` uses `related_name="pins"`).
    A board the requester can't see matches no pins, so the public pins of
    a private board can't be listed by others.
    """

    pins__id = django_filters.NumberFilter(method="filter_board")

    class Meta:
        model = Pin
        fields = ("submitter__username", "tags__name")

    def filter_board(self, queryset, name, value):
        boards = filter_private_board(
            self.request, Board.objects.filter(id=value),
        )
        return queryset.filter(pins__in=boards)


class TagsFilterBackend(BaseFilterBackend):
    """
    Filter pins by several tags: `?tags=a&tags=b`.

    `tags_mode=all` (default) keeps pins carrying every tag,
    `tags_mode=any` keeps pins carrying at least one of them.
    """

    tags_param = "tags"
    mode_param = "tags_mode"
    modes = ("all", "any")

    def filter_queryset(self, request, queryset, view):
        tags = [tag for tag in request.query_params.getlist(self.tags_param) if tag]
        mode = request.query_params.get(self.mode_param, "all")
        if mode not in self.modes:
            raise ValidationError(
                {self.mode_param: "must be one of: %s" % ", ".join(self.modes)}
            )
        if not tags:
            return queryset
        if mode == "any":
            return queryset.filter(tags__name__in=tags).distinct()
        for tag in tags:
            queryset = queryset.filter(tags__name=tag)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name=self.tags_param,
                required=False,
                location="query",
                schema=coreschema.Array(
                    title="Tags",
                    description="Tag name, repeat the parameter for several tags",
                ),
            ),
            coreapi.Field(
                name=self.mode_param,
                required=False,
                location="query",
                schema=coreschema.Enum(
                    self.modes,
                    title="Tags mode",
                    description="'all' (default): pins with every tag; "
                                "'any': pins with at least one tag",
                ),
            ),
        ]
