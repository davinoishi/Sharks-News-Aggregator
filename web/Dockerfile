FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Development command (use npm run build && npm start for production)
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]
