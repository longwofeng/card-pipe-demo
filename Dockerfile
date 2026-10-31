FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests
COPY assets ./assets
COPY rules.yaml ./
COPY README.md ./

RUN mkdir -p out

# 内置中文字体随镜像一起 COPY，不依赖 apt 源；缺字体会在运行时以退出码 3 失败
ENTRYPOINT ["python", "-m", "app.cli"]
CMD ["demo", "--out", "out/acceptance"]
