from django.urls import path
from .views import upload_arquivo, iniciar_processamento, sse_processamento, lista_arquivos, arquivos_processados

urlpatterns = [
    path("", upload_arquivo, name="upload"),
    path("processar/<int:arquivo_id>/", iniciar_processamento, name="iniciar_processamento"),  
    path("sse-processamento/<int:arquivo_id>/", sse_processamento, name="sse_processamento"),
    path("arquivos/", lista_arquivos, name="lista_arquivos"),
    path("arquivos-processados/<int:arquivo_id>/", arquivos_processados, name="arquivos_processados"),  # ✅ Adicionada a nova rota
]
