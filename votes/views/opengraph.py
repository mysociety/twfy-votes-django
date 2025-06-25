import html
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from votes.models import Division, Membership

IMAGE_WIDTH, IMAGE_HEIGHT = 1200, 627
DOT_SIZE = 10
GRID_SIZE = 5  # 5x5 grid
GRID_SPACING = 15  # Space between grids
GROUP_SPACING = 30  # Space between grid groups
DOT_SPACING = 3  # Spacing between dots
MARGIN = 40
TOP_MARGIN = 25
FOOTER_MARGIN = 40  # Space reserved at the bottom for the footer
BACKGROUND_COLOR = "#f3f1eb"


class ColourSettings(NamedTuple):
    colour: str
    border_colour: str = ""


class TextDimensions(NamedTuple):
    width: float
    height: float


colours = {
    "ceidwadwyr": ColourSettings(colour="#166FD2"),
    "conservative": ColourSettings(colour="#166FD2"),
    "labour": ColourSettings(colour="#EE3224"),
    "llafur": ColourSettings(colour="#EE3224"),
    "labourco-operative": ColourSettings(colour="#EE3224"),
    "labour-co-operative": ColourSettings(colour="#EE3224"),
    "democratiaid-rhyddfrydol": ColourSettings(colour="#FFBB33"),
    "liberal-democrat": ColourSettings(colour="#FFBB33"),
    "scottish-national-party": ColourSettings(
        colour="#FDF38E", border_colour="#7E7A47"
    ),
    "plaid-cymru": ColourSettings(colour="#E0861A"),
    "green": ColourSettings(colour="#6AB023"),
    "dup": ColourSettings(colour="#193264"),
    "social-democratic-and-labour-party": ColourSettings(colour="#3C783C"),
    "independent": ColourSettings(colour="#666666"),
    "reform": ColourSettings(colour="#12B6CF"),
    "uup": ColourSettings(colour="#A6A6A6"),
    "traditional-unionist-voice": ColourSettings(colour="#A6A6A6"),
    "alliance": ColourSettings(colour="#F2C94C"),
}


def fetch_merriweather():
    """
    Ensure we have a local copy of the merriweather font
    """
    font_dest = Path("/usr/local/share/fonts/truetype/merriweather/Merriweather.ttf")
    if not font_dest.exists():
        raise ValueError("Merriweather font not found, please install it.")
    return font_dest


def simplify_votes_df(division: Division) -> pd.DataFrame:
    division.votes_df()

    relevant_memberships = Membership.objects.filter(
        chamber=division.chamber,
        start_date__lte=division.date,
        end_date__gte=division.date,
    ).prefetch_related("party", "person")
    person_to_membership_map = {x.person_id: x for x in relevant_memberships}

    data = [
        {
            "party": person_to_membership_map[v.person_id].party.slug,
            "vote": v.vote_desc(),
        }
        for v in division.votes.all().prefetch_related("person")
    ]

    df = pd.DataFrame(data)

    df["background_colour"] = df["party"].map(
        lambda x: colours[x].colour if x in colours else "#666666"
    )

    # set the bordercolour to the same as the background colour if not defined
    df["border_colour"] = df["party"].map(
        lambda x: colours[x].border_colour if x in colours else "#666666"
    )
    df["border_colour"] = df.apply(
        lambda x: (
            x["background_colour"] if x["border_colour"] == "" else x["border_colour"]
        ),
        axis=1,
    )

    df = df.sort_values(
        by=["party", "vote"],
        ascending=[True, True],
    )

    return df


def create_canvas(
    width: int = IMAGE_WIDTH,
    height: int = IMAGE_HEIGHT,
    bg_color: str = BACKGROUND_COLOR,
) -> Image.Image:
    """Creates a blank canvas with the specified dimensions and background color."""
    return Image.new("RGB", (width, height), bg_color)


def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Returns a font object with the specified path and size."""
    return ImageFont.truetype(font_path, size)


def get_text_dimensions(font: ImageFont.FreeTypeFont, text: str) -> TextDimensions:
    """Gets the width and height of text using a specific font."""
    bbox = font.getbbox(text)
    return TextDimensions(width=bbox[2] - bbox[0], height=bbox[3] - bbox[1])


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str = "black",
    width: int = IMAGE_WIDTH,
) -> float:
    """Draws text centered horizontally at the specified y position."""
    dimensions = get_text_dimensions(font=font, text=text)
    x_position = (width - dimensions.width) // 2
    draw.text((x_position, y), text, fill=color, font=font)
    return dimensions.width


def fit_text_to_width(
    font_path: Path, font_size: int, text: str, max_width: int
) -> ImageFont.FreeTypeFont:
    """Returns a font that will render the text within the specified width."""
    font = get_font(font_path=font_path, size=font_size)
    dimensions = get_text_dimensions(font=font, text=text)

    while dimensions.width > max_width:
        font_size -= 1
        font = get_font(font_path=font_path, size=font_size)
        dimensions = get_text_dimensions(font=font, text=text)

    return font


def draw_dot_grid(
    draw: ImageDraw.ImageDraw,
    group: pd.DataFrame,
    vote_start_y: float,
    grids_per_row: int,
) -> float:
    """Draws a grid of dots for a vote type."""
    dots_per_full_grid = GRID_SIZE * GRID_SIZE
    max_y_this_section = vote_start_y

    for dot_index, (_, row) in enumerate(group.iterrows()):
        # Calculate the current grid
        current_grid = dot_index // dots_per_full_grid

        # Calculate the grid's row and column
        grid_row = current_grid // grids_per_row
        grid_col = current_grid % grids_per_row

        # Calculate position within the grid
        in_grid_index = dot_index % dots_per_full_grid
        in_grid_row = in_grid_index // GRID_SIZE
        in_grid_col = in_grid_index % GRID_SIZE

        # Calculate the actual x and y coordinates for this dot - left aligned at MARGIN
        single_grid_width = GRID_SIZE * (DOT_SIZE + DOT_SPACING) - DOT_SPACING
        x = (
            MARGIN
            + grid_col * (single_grid_width + GRID_SPACING)
            + in_grid_col * (DOT_SIZE + DOT_SPACING)
        )
        y = (
            vote_start_y
            + grid_row * (GRID_SIZE * (DOT_SIZE + DOT_SPACING) + GRID_SPACING)
            + in_grid_row * (DOT_SIZE + DOT_SPACING)
        )

        # Draw the dot
        background_colour = row["background_colour"]
        border_colour = row["border_colour"]
        draw.ellipse(
            [x, y, x + DOT_SIZE, y + DOT_SIZE],
            fill=background_colour,
            outline=border_colour,
            width=1,  # Ensure the border is smooth
        )

        # Keep track of the maximum y-coordinate used
        max_y_this_dot = y + DOT_SIZE
        if max_y_this_dot > max_y_this_section:
            max_y_this_section = max_y_this_dot

    return max_y_this_section


def draw_footer(draw: ImageDraw.ImageDraw, font_path: Path) -> None:
    """Draw the TheyWorkForYou Votes footer with 'You' bolded."""
    footer_text_part1 = "TheyWorkFor"
    footer_text_part2 = "You"
    footer_text_part3 = " Votes"
    footer_font = get_font(font_path=font_path, size=27)
    footer_bold_font = get_font(font_path=font_path, size=27)

    # Get dimensions for each part
    part1_dims = get_text_dimensions(font=footer_font, text=footer_text_part1)
    part2_dims = get_text_dimensions(font=footer_bold_font, text=footer_text_part2)
    part3_dims = get_text_dimensions(font=footer_font, text=footer_text_part3)

    # Calculate total width and positions
    total_width = part1_dims.width + part2_dims.width + part3_dims.width
    footer_x = IMAGE_WIDTH - total_width - MARGIN
    footer_y = IMAGE_HEIGHT - part1_dims.height - MARGIN

    # Draw each part
    draw.text((footer_x, footer_y), footer_text_part1, fill="black", font=footer_font)
    draw.text(
        (footer_x + part1_dims.width, footer_y),
        footer_text_part2,
        fill="black",
        font=footer_bold_font,
    )
    draw.text(
        (footer_x + part1_dims.width + part2_dims.width, footer_y),
        footer_text_part3,
        fill="black",
        font=footer_font,
    )


def draw_vote_image(division: Division) -> Image.Image:
    """
    Main function to create the vote visualization
    """
    # Setup
    df = simplify_votes_df(division)
    merriweather_font_path = fetch_merriweather()
    image = create_canvas()
    draw = ImageDraw.Draw(image)

    # Draw division title
    division_name = html.unescape(division.safe_decision_name())
    max_text_width = int(IMAGE_WIDTH * 0.95)
    title_font = fit_text_to_width(
        font_path=merriweather_font_path,
        font_size=60,
        text=division_name,
        max_width=max_text_width,
    )
    dimensions = get_text_dimensions(font=title_font, text=division_name)

    # Draw centered title
    x_position = (IMAGE_WIDTH - dimensions.width) // 2
    draw.text((x_position, TOP_MARGIN), division_name, fill="black", font=title_font)

    # Draw division date
    division_date = division.date.strftime(
        "%d %B %Y"
    )  # British format: "10 April 2025"
    date_dimensions = get_text_dimensions(font=title_font, text=division_date)
    date_y_position = TOP_MARGIN + dimensions.height + 20
    date_x_position = (IMAGE_WIDTH - date_dimensions.width) // 2
    draw.text(
        (date_x_position, date_y_position), division_date, fill="black", font=title_font
    )

    # Start position for vote sections
    section_y_start = date_y_position + date_dimensions.height + 35
    max_y_used = section_y_start

    # Create label font
    label_font = get_font(font_path=merriweather_font_path, size=30)

    # Calculate grid layout
    single_grid_width = GRID_SIZE * (DOT_SIZE + DOT_SPACING) - DOT_SPACING
    available_width = IMAGE_WIDTH - 2 * MARGIN
    single_grid_with_spacing = single_grid_width + GRID_SPACING
    grids_per_row = max(1, min(10, available_width // single_grid_with_spacing))

    # Filter votes by type

    absent_count = len(df[df["vote"] == "Absent"])
    abstain_count = len(df[df["vote"] == "Abstain"])
    aye_count = len(df[df["vote"] == "Aye"])
    no_count = len(df[df["vote"] == "No"])

    # Check if we should include "Absent" votes
    # We can include absent dots if each of Aye and No take up one line
    # We can include just the total if aye + no is only 3 lines between them
    include_absent_dots = aye_count <= 250 and no_count <= 250 and absent_count <= 250

    # Simple calculation for available height
    total_votes = aye_count + no_count + (absent_count if include_absent_dots else 0)
    # Estimate if we have enough space for all content plus labels
    include_absent_title = (total_votes < 550) or (
        absent_count > 0 and total_votes < 650
    )
    has_abstain_votes = abstain_count > 0

    # Prepare the dataframe for display
    if include_absent_dots:
        # Create a new DataFrame with Aye, No and Absent votes
        display_dots_for = ["Aye", "No", "Absent"]
    else:
        display_dots_for = ["Aye", "No"]

    if include_absent_title:
        vote_types_to_include = ["Aye", "No", "Absent"]
        if has_abstain_votes:
            vote_types_to_include.append("Abstain")
    else:
        vote_types_to_include = ["Aye", "No"]

    filtered_df = df[df["vote"].isin(vote_types_to_include)]
    # Group by vote type
    votes_by_type = filtered_df.groupby("vote")

    # Define the order of vote types
    vote_order = ["Aye", "No", "Absent"]

    # Define which vote types should display dots

    # Process vote types in specific order
    for vote_type in vote_order:
        # Skip if this vote type is not in the filtered data
        if vote_type not in votes_by_type.groups:
            continue

        # Get the group for this vote type
        group = votes_by_type.get_group(vote_type)

        # Sort this group by party count (most common parties first)
        party_counts_in_group = group["party"].value_counts()
        group["party_count"] = group.copy()["party"].map(party_counts_in_group)
        group = group.sort_values(by=["party_count", "party"], ascending=[False, True])

        vote_count = len(group)
        member_plural = division.chamber.member_plural

        # Special handling for Absent + Abstain when both are present
        if vote_type == "Absent" and "Abstain" in votes_by_type.groups:
            abstain_group = votes_by_type.get_group("Abstain")
            abstain_count = len(abstain_group)
            vote_label = f"Absent: {vote_count} {member_plural}, Abstain: {abstain_count} {member_plural}"
        else:
            # Skip "Abstain" as it's handled with "Absent"
            if vote_type == "Abstain":
                continue
            vote_label = f"{vote_type}: {vote_count} {member_plural}"

        # Draw vote label
        label_dimensions = get_text_dimensions(font=label_font, text=vote_label)
        draw.text((MARGIN, max_y_used), vote_label, fill="black", font=label_font)
        vote_start_y = max_y_used + label_dimensions.height + 15

        # Simple adaptive spacing based on total votes
        if total_votes > 500:
            # For large numbers of votes, use smaller spacing
            adjusted_group_spacing = max(10, GROUP_SPACING // 2)
        else:
            adjusted_group_spacing = GROUP_SPACING

        # Only draw dots grid for displayed types
        if vote_type in display_dots_for:
            # Draw dots for this vote type
            max_y_this_section = draw_dot_grid(
                draw=draw,
                group=group,
                vote_start_y=vote_start_y,
                grids_per_row=grids_per_row,
            )

            # Update the max_y_used to include the height of the grid
            max_y_used = max_y_this_section + adjusted_group_spacing

            # Simple boundary check to ensure we have space for the footer
            if max_y_used > IMAGE_HEIGHT - FOOTER_MARGIN:
                max_y_used = (
                    max_y_this_section + 5
                )  # Minimal spacing when close to boundary
        else:
            # For Absent and Abstain, just update max_y_used past the label
            max_y_used = vote_start_y + adjusted_group_spacing

    # Final check to ensure footer has enough space
    footer_height = 40  # Approximate height needed for footer
    if max_y_used > IMAGE_HEIGHT - footer_height - 10:
        max_y_used = IMAGE_HEIGHT - footer_height - 10

    # Draw footer with "You" bolded
    draw_footer(draw=draw, font_path=merriweather_font_path)

    return image


def draw_custom_image(
    header: str, subheader: str = "", include_logo: bool = True
) -> Image.Image:
    """
    Create an image with custom header and subheader text, centered vertically and horizontally
    """
    merriweather_font_path = fetch_merriweather()
    image = create_canvas()
    draw = ImageDraw.Draw(image)

    # Calculate maximum text width
    max_text_width = int(IMAGE_WIDTH * 0.95)

    # Fit header text to width and get dimensions
    header_font = fit_text_to_width(
        font_path=merriweather_font_path,
        font_size=60,
        text=header,
        max_width=max_text_width,
    )
    header_dims = get_text_dimensions(font=header_font, text=header)

    # Fit subheader text to width and get dimensions
    subheader_font = fit_text_to_width(
        font_path=merriweather_font_path,
        font_size=60,
        text=subheader,
        max_width=max_text_width,
    )
    subheader_dims = get_text_dimensions(font=subheader_font, text=subheader)

    # Calculate total height of header, subheader, and spacing
    total_text_height = header_dims.height + subheader_dims.height + 20

    # Calculate starting y position to center the text vertically
    start_y = (IMAGE_HEIGHT - total_text_height) // 2

    # Draw header centered horizontally
    header_x = (IMAGE_WIDTH - header_dims.width) // 2
    draw.text((header_x, start_y), header, fill="black", font=header_font)

    # Draw subheader centered horizontally below header
    subheader_x = (IMAGE_WIDTH - subheader_dims.width) // 2
    subheader_y = start_y + header_dims.height + 20
    draw.text((subheader_x, subheader_y), subheader, fill="black", font=subheader_font)

    if include_logo:
        # Draw footer with "You" bolded
        draw_footer(draw=draw, font_path=merriweather_font_path)

    return image
