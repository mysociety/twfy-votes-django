import calendar
import re
from typing import Any
from urllib.parse import urlencode

from django import template
from django.contrib.auth import get_user_model
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe

import markdown
import pandas as pd

register = template.Library()
User = get_user_model()


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
        percentage_columns = []

    def format_percentage(value: float):
        # if value is na return "-"
        if pd.isna(value):
            return "-"
        return "{:.2%}".format(value)

    df = df.rename(columns=nice_headers)

    styled_df = df.style.hide(axis="index").format(  # type: ignore
        formatter={x: format_percentage for x in percentage_columns}  # type: ignore
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


class MarkdownNode(template.Node):
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

        text = markdown.markdown(markdown_text, extensions=["toc"])
        return text


@register.tag(name="case")
def case_tag(parser, token):
    pass


@register.tag(name="switch")
def switch_tag(parser, token):
    """
    The ``{% switch %}`` tag compares a variable against one or more values in
    ``{% case %}`` tags, and outputs the contents of the matching block.  An
    optional ``{% else %}`` tag sets off the default output if no matches
    could be found::

        {% switch result_count %}
            {% case 0 %}
                There are no search results.
            {% case 1 %}
                There is one search result.
            {% else %}
                Jackpot! Your search found {{ result_count }} results.
        {% endswitch %}

    Each ``{% case %}`` tag can take multiple values to compare the variable
    against::

        {% switch username %}
            {% case "Jim" "Bob" "Joe" %}
                Me old mate {{ username }}! How ya doin?
            {% else %}
                Hello {{ username }}
        {% endswitch %}
    """
    bits = token.contents.split()
    tag_name = bits[0]
    if len(bits) != 2:
        raise template.TemplateSyntaxError("'%s' tag requires one argument" % tag_name)
    variable = parser.compile_filter(bits[1])

    class BlockTagList(object):
        # This is a bit of a hack, as it embeds knowledge of the behaviour
        # of Parser.parse() relating to the "parse_until" argument.
        def __init__(self, *names):
            self.names = set(names)

        def __contains__(self, token_contents):
            name = token_contents.split()[0]
            return name in self.names

    # Skip over everything before the first {% case %} tag
    # TODO: error if there is anything here!
    parser.parse(BlockTagList("case", "endswitch"))

    cases = []
    token = parser.next_token()
    got_case = False
    got_else = False
    while token.contents != "endswitch":
        nodelist = parser.parse(BlockTagList("case", "else", "endswitch"))

        if got_else:
            raise template.TemplateSyntaxError(
                "'else' must be last tag in '%s'." % tag_name
            )

        contents = token.split_contents()
        token_name, token_args = contents[0], contents[1:]

        if token_name == "case":
            tests = map(parser.compile_filter, token_args)
            case = (tests, nodelist)
            got_case = True
        else:
            # The {% else %} tag
            assert token_name == "else"
            case = (None, nodelist)
            got_else = True
        cases.append(case)
        token = parser.next_token()

    if not got_case:
        raise template.TemplateSyntaxError(
            "'%s' must have at least one 'case'." % tag_name
        )

    return SwitchNode(variable, cases)


class SwitchNode(template.Node):
    def __init__(self, variable, cases):
        self.variable = variable
        self.cases = cases

    def __repr__(self):
        return "<Switch node>"

    def __iter__(self):
        for tests, nodelist in self.cases:
            for node in nodelist:
                yield node

    def get_nodes_by_type(self, nodetype):
        nodes = []
        if isinstance(self, nodetype):
            nodes.append(self)
        for tests, nodelist in self.cases:
            nodes.extend(nodelist.get_nodes_by_type(nodetype))
        return nodes

    def render(self, context):
        value_missing = False
        value = self.variable.resolve(context, True)

        for tests, nodelist in self.cases:
            if tests is None:
                return nodelist.render(context)
            elif not value_missing:
                for test in tests:
                    test_value = test.resolve(context, True)
                    if value == test_value:
                        return nodelist.render(context)

        assert False, f"No case hit for value {value}"
