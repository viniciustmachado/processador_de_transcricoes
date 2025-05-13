from django.db import models


class ArquivoProcessado(models.Model):
    """Armazena os arquivos enviados pelo usuário"""

    arquivo_original = models.FileField(upload_to="uploads/")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.arquivo_original.name


class ChunkProcessado(models.Model):
    """Armazena cada parte processada de um arquivo"""

    arquivo = models.ForeignKey(
        ArquivoProcessado, related_name="chunks", on_delete=models.CASCADE
    )
    chunk_arquivo = models.FileField(upload_to="processados/")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chunk de {self.arquivo.arquivo_original.name}"
