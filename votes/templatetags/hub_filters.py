import calendar
import re
from typing import Any
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.template import Library, Node, TemplateSyntaxError
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe

import markdown
import pandas as pd

from votes.views.auth import super_users_or_group

register = Library()
User = get_user_model()


@register.filter(name="replace_underscore_with_hyphen")
def replace_underscore_with_hyphen(value: str) -> str:
    """Replaces underscores with hyphens in a string."""
    if isinstance(value, str):
        return value.replace("_", "-")
    return value


@register.filter(name="split")
def split(value: str, key: str):
    return value.split(key)


@register.filter(name="splitlines")
def splitlines(value: str):
    return value.splitlines()


@register.filter(name="highlight")
def highlight(text: str, search: str):
    try:
        rgx = re.compile(re.escape(search), re.IGNORECASE)
        html = rgx.sub(lambda m: f"<mark>{m.group()}</mark>", text)
        return mark_safe(html)
    except TypeError:
        # search is probably None
        return text


@register.filter
@stringfilter
def domain_human(value: str):
    return re.sub(r"^(https?:[/][/])?(www[.])?([^/]+).*", r"\3", value)


@register.filter
@stringfilter
def url_human(value: str):
    return re.sub(r"^(https?:[/][/])?(www[.])?(.*)", r"\3", value)


@register.filter
@stringfilter
def simplify_dataset_name(value: str):
    trimmed = re.sub(r"^Number of ", "", value)
    return trimmed[0].upper() + trimmed[1:]


@register.filter
@stringfilter
def prevent_widow(s: str, max: int = 12):
    # Replace final space in string with &nbsp;
    # if length of final two words (plus a space)
    # is less than `max` value.
    bits = s.rsplit(" ", 2)
    if len(f"{bits[-2]} {bits[-1]}") < max:
        return mark_safe(f"{bits[-3]} {bits[-2]}&nbsp;{bits[-1]}")
    else:
        return s


@register.simple_tag
def urlencode_params(**kwargs: Any):
    """
    Return encoded URL parameters
    """
    return urlencode(kwargs)


@register.simple_tag
def pending_account_requests(**kwargs: Any):
    """
    Return number of account requests
    """
    return User.objects.filter(
        is_active=False,
        userproperties__email_confirmed=True,
        userproperties__account_confirmed=False,
    ).count()


@register.filter
def month_name(month_number: int):
    return calendar.month_name[month_number]


def nice_headers(s: str) -> str:
    s = s.replace("_", " ")
    return s


@register.simple_tag
def style_df(df: pd.DataFrame, *percentage_columns: str) -> str:
    if percentage_columns is None:
        percentage_columns = []  # type: ignore
    else:
        percentage_columns = list(percentage_columns)  # type: ignore

    def format_percentage(value: float):
        # if value is na return "n/a"
        if pd.isna(value):
            return "n/a"
        if isinstance(value, str):
            return value
        return "{:.2%}".format(value)

    df = df.rename(columns=nice_headers)

    percentage_columns = tuple([x for x in percentage_columns if x in df.columns])

    styled_df = df.style.hide(axis="index").format(
        {x: format_percentage for x in percentage_columns},  # type: ignore
        precision=2,
    )

    return mark_safe(styled_df.to_html())  # type: ignore


@register.tag(name="markdown")
def markdown_tag(parser, token):
    """
    Between {% markdown %} and {% endmarkdown %} tags,
    render the text as markdown.

    Django tags used within the markdown will be rendered first.
    """
    nodelist = parser.parse(("endmarkdown",))
    parser.delete_first_token()
    return MarkdownNode(nodelist)


class MarkdownNode(Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        # render items below in the stack into markdown
        markdown_text = self.nodelist.render(context)

        # if the text is indented, we want to remove the indentation so that the smallest indent becomes 0, but all others are relative to that
        # this is so that we can have indented code blocks in markdown
        # we do this by finding the smallest indent, and then removing that from all lines

        smallest_indent = None
        for line in markdown_text.splitlines():
            if line.strip() == "":
                continue
            indent = len(line) - len(line.lstrip())
            if smallest_indent is None or indent < smallest_indent:
                smallest_indent = indent

        # remove the smallest indent from all lines
        if smallest_indent is not None:
            markdown_text = "\n".join(
                [line[smallest_indent:] for line in markdown_text.splitlines()]
            )

        # add an extra line space between all new lines
        markdown_text = markdown_text.replace("\n", "\n\n\n")

        text = markdown.markdown(markdown_text, extensions=["toc"])
        return text


class DraftNode(Node):
    """
    Node class to conditionally render content inside {% draft %}...{% enddraft %}
    """

    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        if context.get("can_view_draft_content"):
            return self.nodelist.render(context)
        return ""


@register.tag(name="draft")
def do_draft(parser, token):
    """
    Custom template block tag: {% draft %}...{% enddraft %}
    Renders content only if the user has draft access.
    """
    nodelist = parser.parse(("enddraft",))  # Parse until {% enddraft %}
    parser.delete_first_token()  # Remove 'enddraft'
    return DraftNode(nodelist)


class UserFlagNode(Node):
    """
    Node class to conditionally render content inside {% userflag "flag_name" %}...{% enduserflag %}
    """

    def __init__(self, nodelist, flag_name):
        self.nodelist = nodelist
        self.flag_name = flag_name

    def render(self, context):
        request = context.get("request")
        if not request:
            return ""
        if super_users_or_group(request.user, self.flag_name):
            return self.nodelist.render(context)
        return ""


@register.tag(name="featureflag")
def do_userflag(parser, token):
    """
    Custom template block tag: {% featureflag pg.ADVANCED_INFO %}...{% endfeatureflag %}
    Renders content only if the user has the specified flag access.
    """
    try:
        tag_name, flag_name = token.split_contents()
    except ValueError:
        raise TemplateSyntaxError(
            "%r tag requires a single argument" % token.contents.split()[0]
        )
    nodelist = parser.parse(("endfeatureflag",))
    parser.delete_first_token()
    return UserFlagNode(nodelist, flag_name.strip('"'))
