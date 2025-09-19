import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate SVG sprite from individual SVG files'
    output = Path("templates") / Path("all-sprites.svg")
    directory = Path("sprites")

    def handle(self, *args, **options):
        # Get the directory of the management command
        output_file = Path(settings.BASE_DIR) / self.output

        # Set input directory (default to script directory)
        input_dir = Path(settings.BASE_DIR) / self.directory

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Start building the SVG sprite
        svg_content = '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" class="hidden">'

        # Process all SVG files in the input directory
        svg_files = sorted(input_dir.glob('*.svg'))

        for svg_file in svg_files:
            # Skip the output file if it's in the same directory
            if not str(svg_file).endswith("svg"):
                continue

            # Get the ID from filename (without .svg extension)
            file_id = svg_file.stem

            # Read the SVG file
            with open(svg_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract <svg> attributes (excluding xmlns)
            svg_tag_match = re.search(r'<svg([^>]*)>', content)
            attributes = ''
            if svg_tag_match:
                attrs = svg_tag_match.group(1)
                # Remove xmlns attribute
                attrs = re.sub(r'\s+xmlns="[^"]*"', '', attrs)
                # Remove viewBox attribute
                #attrs = re.sub(r'\s+viewBox="[^"]*"', '', attrs)
                attrs = re.sub(r'\s+width="[^"]*"', '', attrs)
                attrs = re.sub(r'\s+height="[^"]*"', '', attrs)
                attrs = attrs.replace('stroke="#000000" ', 'stroke="currentColor" ')
                attributes = attrs

            # Remove newlines and extra spaces
            content = re.sub(r'\n', ' ', content)
            content = re.sub(r'\s+', ' ', content)

            # Remove <svg> opening and closing tags
            content = re.sub(r'<svg[^>]*>', '', content)
            content = re.sub(r'</svg>', '', content)

            # Build the symbol tag
            symbol = f'<symbol id="{file_id}"{attributes}>{content}</symbol>'

            svg_content += f'\n{symbol}'

        # Close the SVG sprite
        svg_content += '\n</svg>'

        # Write to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        self.stdout.write(
            self.style.SUCCESS(f'SVG sprite created: {output_file}')
        )