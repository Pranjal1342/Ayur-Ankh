FROM ubuntu:22.04

# ... (keep all previous lines the same up to COPY . .)
COPY . .

# --- ADD THESE NEW LINES AT THE END ---
# Make the start script executable
RUN chmod +x start.sh

# Tell Render to run this script when the container starts
CMD ["./start.sh"]