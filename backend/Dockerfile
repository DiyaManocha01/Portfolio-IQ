# PortfolioIQ backend image.
#
# Builds the FastAPI app with its full ML/data-science dependency stack
# (pandas, scikit-learn, xgboost, shap, pyportfolioopt, ...). All of
# these packages publish manylinux wheels for standard x86_64/aarch64
# Linux + CPython 3.11, so no C toolchain is needed in the image itself;
# psycopg2-binary also bundles its own libpq, so no separate Postgres
# client library is needed either. If a future dependency ever lacks a
# wheel for your platform, `pip install` will fail with a clear "no
# wheel, needs a compiler" error -- add `apt-get install build-essential`
# back into the build stage at that point, not preemptively.

FROM python:3.11-slim AS build

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

COPY --from=build /install /usr/local

WORKDIR /app
COPY . .

RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
