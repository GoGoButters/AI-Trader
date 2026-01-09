FROM nginx:alpine

# Copy the WebUI
COPY index.html /usr/share/nginx/html/

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
