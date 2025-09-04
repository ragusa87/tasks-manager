#!/bin/bash

# Get the directory of the script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

# Output file
OUTPUT_FILE="$SCRIPT_DIR/../templates/all-sprites.svg"
# Start the SVG sprite
echo -n '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" class="hidden">' > "$OUTPUT_FILE"

# Loop through all SVG files, skipping OUTPUT_FILE
for file in *.svg; do
    [[ $(basename "$file") == "$OUTPUT_FILE" ]] && continue

    ID=$(basename "$file" .svg)

    # Extract <svg> attributes (excluding xmlns)
    ATTRIBUTES=$(grep -o '<svg[^>]*>' "$file" | sed -E 's/<svg([^>]*)>/\1/' | sed -E 's/\s+xmlns="[^"]*"//g')

    # Remove newlines, extra spaces, and strip <svg> tags
    CONTENT=$(sed -e ':a;N;$!ba;s/\n/ /g' -e 's/\s\+/ /g' -e 's/<svg[^>]*>//' -e 's/<\/svg>//' "$file")

    # Construct the symbol tag with extracted attributes (without xmlns)
    SYMBOL="<symbol id=\"$ID\"$ATTRIBUTES>$CONTENT</symbol>"

    printf "\n" >> "$OUTPUT_FILE"
    echo -n "$SYMBOL" >> "$OUTPUT_FILE"
done

# Close the SVG sprite
printf "\n" >> "$OUTPUT_FILE"
echo '</svg>' >> "$OUTPUT_FILE"

echo "SVG sprite created: $OUTPUT_FILE"
