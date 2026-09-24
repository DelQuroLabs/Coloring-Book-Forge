FROM python:3.12-slim
WORKDIR /app
COPY server.py Coloring_Book_Forge.html index.html coloring_prompts_master_36000.json ./
COPY sample_pages/ sample_pages/
COPY niche_packs/ niche_packs/
RUN mkdir -p output_production
EXPOSE 8080
ENV PORT=8080
CMD ["python3", "server.py"]
