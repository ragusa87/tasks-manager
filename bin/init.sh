#!/bin/bash
set -e
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments
FORCE=false
DOMAIN_NAME=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE=true
            shift
            ;;
        --domain)
            DOMAIN_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -f, --force       Force overwrite without prompting"
            echo "  --domain DOMAIN   Set domain name (e.g., example.com)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Check if example file exists
if [ ! -f "docker-compose.override.example.yaml" ]; then
    echo -e "${RED}Error: docker-compose.override.example.yaml not found!${NC}"
    exit 1
fi

echo -e "${GREEN}=== Docker Compose Override Initialization ===${NC}\n"




# Check if docker-compose.override.yaml already exists
if [ -f "docker-compose.override.yaml" ]; then
    if [ "$FORCE" = false ]; then
        echo -e "${YELLOW}Warning: docker-compose.override.yaml already exists!${NC}"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Aborted.${NC}"
            exit 1
        fi

        echo "To initialize the database with a new password, I need to remove the database volume."
        read -p "Are you sure you want to continue? This will delete all database data! (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Aborted.${NC}"
            exit 1
        fi
        echo -e "${YELLOW}Stopping containers and removing database volume...${NC}"
        docker compose down
        docker volume rm tasks-manager_postgres_data 2>/dev/null || true
    else
        echo -e "${YELLOW}Force flag detected. Overwriting existing docker-compose.override.yaml...${NC}"
        echo -e "${YELLOW}Stopping containers and removing database volume...${NC}"
        docker compose down
        docker volume rm tasks-manager_postgres_data 2>/dev/null || true
    fi
    echo -e "${YELLOW}Creating backup as docker-compose.override.yaml.backup${NC}"
    cp -f docker-compose.override.yaml docker-compose.override.yaml.backup
fi



echo -e "${GREEN}Copying docker-compose.override.example.yaml...${NC}"
cp docker-compose.override.example.yaml docker-compose.override.yaml

# Ask for domain name if not provided
if [ -z "$DOMAIN_NAME" ]; then
    echo -e "${YELLOW}Enter the domain name that will be used (e.g., example.com):${NC}"
    read -p "Domain: " DOMAIN_NAME

    # Validate domain name is not empty
    while [ -z "$DOMAIN_NAME" ]; do
        echo -e "${RED}Domain name cannot be empty!${NC}"
        read -p "Domain: " DOMAIN_NAME
    done
fi

echo -e "${GREEN}Using domain: $DOMAIN_NAME${NC}"

# Generate secure random values
echo -e "${GREEN}Generating secure credentials...${NC}"

# Generate Django SECRET_KEY (using Python if available, otherwise openssl)
if command -v uv &> /dev/null; then
    SECRET_KEY=$(uv run python3 -c 'import random; import string; print("".join(random.SystemRandom().choice(string.ascii_letters + string.digits + string.punctuation.replace("\"", "").replace("\\", "")) for _ in range(50)))')
else
    SECRET_KEY=$(openssl rand -base64 48 | tr -d "=+/" | cut -c1-50)
fi

# Generate database password
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

# Generate random ports (range 10000-60000 to avoid common ports)
PORT_5432=$((RANDOM % 50000 + 10000))
PORT_6379=$((RANDOM % 50000 + 10000))
PORT_8000=$((RANDOM % 50000 + 10000))

# Make sure ports are different
while [ $PORT_6379 -eq $PORT_5432 ]; do
    PORT_6379=$((RANDOM % 50000 + 10000))
done
while [ $PORT_8000 -eq $PORT_5432 ]; do
    PORT_8000=$((RANDOM % 50000 + 10000))
done

# Get user and group IDs
USER_ID=$(id -u)
GROUP_ID=$(id -g)

echo -e "${GREEN}Replacing placeholder values...${NC}"

# Escape special characters for sed (including the delimiter #)
# Also escape $ to prevent Docker Compose from treating it as a variable
SECRET_KEY_ESCAPED=$(echo "$SECRET_KEY" | sed 's/[&#/\$]/\\&/g' | sed 's/\$/\$\$/g')
DB_PASSWORD_ESCAPED=$(echo "$DB_PASSWORD" | sed 's/[&#/\]/\\&/g')

# Replace SECRET_KEY
sed -i "s#SECRET_KEY=your-custom-secret-key-here-min-50-chars-random-string#SECRET_KEY=$SECRET_KEY_ESCAPED#g" docker-compose.override.yaml

# Replace DB_PASSWORD
sed -i "s#DB_PASSWORD=your-secure-database-password-here#DB_PASSWORD=$DB_PASSWORD_ESCAPED#g" docker-compose.override.yaml

# Replace POSTGRES_PASSWORD
sed -i "s#POSTGRES_PASSWORD: your-secure-database-password-here#POSTGRES_PASSWORD: $DB_PASSWORD_ESCAPED#g" docker-compose.override.yaml

# Replace ALLOWED_HOSTS with domain name
sed -i "s#ALLOWED_HOSTS=tasks.example.com#ALLOWED_HOSTS=$DOMAIN_NAME#g" docker-compose.override.yaml

# Replace Traefik router rule with domain name
sed -i 's#traefik.http.routers.web-import.rule=Host(`tasks.example.com`)#traefik.http.routers.web-import.rule=Host(`'"$DOMAIN_NAME"'`)#g' docker-compose.override.yaml

# Replace USER_ID and GROUP_ID
sed -i "s|USER_ID: 1000|USER_ID: $USER_ID|g" docker-compose.override.yaml
sed -i "s|GROUP_ID: 1000|GROUP_ID: $GROUP_ID|g" docker-compose.override.yaml

# Replace ports with random ones
sed -i "s|\"5432:5432\"|\"$PORT_5432:5432\"|g" docker-compose.override.yaml
sed -i "s|\"6379:6379\"|\"$PORT_6379:6379\"|g" docker-compose.override.yaml
sed -i "s|\"8000:8000\"|\"$PORT_8000:8000\"|g" docker-compose.override.yaml

echo -e "\n${GREEN}✓ docker-compose.override.yaml has been created successfully!${NC}\n"

# Display generated credentials
echo -e "${YELLOW}=== Generated Credentials ===${NC}"
echo -e "Django SECRET_KEY: ${GREEN}[Generated]${NC}"
echo -e "Database Password: ${GREEN}[Generated]${NC}"
echo -e "User ID: ${GREEN}$USER_ID${NC}"
echo -e "Group ID: ${GREEN}$GROUP_ID${NC}"
echo -e "\n${YELLOW}=== Generated Ports ===${NC}"
echo -e "PostgreSQL Port: ${GREEN}$PORT_5432${NC} (mapped to container port 5432)"
echo -e "Redis Port: ${GREEN}$PORT_6379${NC} (mapped to container port 6379)"
echo -e "Web Port: ${GREEN}$PORT_8000${NC} (mapped to container port 8000)"

echo -e "\n${GREEN}=== Initialization Complete ===${NC}"
rm -Rf .venv node_modules
cp -f .env.example .env
docker compose up -d
