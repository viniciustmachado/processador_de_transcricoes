from django.urls import path
from .views import (
    upload_arquivo,
    iniciar_processamento,
    sse_processamento,
    arquivos_processados,
    download_zip,
    download_all_text,
)

urlpatterns = [
    path("", upload_arquivo, name="upload_arquivo"),
    path(
        "processar/<int:arquivo_id>/",
        iniciar_processamento,
        name="iniciar_processamento",
    ),
    path(
        "sse-processamento/<int:arquivo_id>/",
        sse_processamento,
        name="sse_processamento",
    ),
    path(
        "resultados/<int:arquivo_id>/",
        arquivos_processados,
        name="arquivos_processados",
    ),
    path(
        "resultados/<int:arquivo_id>/download-zip/", download_zip, name="download_zip"
    ),
    path(
        "resultados/<int:arquivo_id>/download-all/",
        download_all_text,
        name="download_all_text",
    ),
]
