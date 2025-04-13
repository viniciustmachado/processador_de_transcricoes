import os
import time
import openai
from django.http import StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import ArquivoProcessado, ChunkProcessado  # 🟢 Importação corrigida

# 🔹 Definição da chave da API OpenAI (⚠️ Certifique-se de não expô-la publicamente)
from dotenv import load_dotenv
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")



def upload_arquivo(request):
    """ Página de upload de arquivos """
    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if arquivo:
            novo_arquivo = ArquivoProcessado(arquivo_original=arquivo)
            novo_arquivo.save()
            # 🟢 Redireciona para a página de acompanhamento em tempo real
            return redirect("iniciar_processamento", arquivo_id=novo_arquivo.id)
    return render(request, "upload.html")


def processar_arquivo(request, arquivo_id):
    """ Processa o arquivo enviado e salva os chunks no banco de dados """
    arquivo = get_object_or_404(ArquivoProcessado, id=arquivo_id)
    caminho = arquivo.arquivo_original.path

    with open(caminho, "r", encoding="utf-8") as f:
        texto = f.read()

    chunks = chunk_text(texto)
    logs = []
    
    pasta_processados = "media/processados/"
    os.makedirs(pasta_processados, exist_ok=True)

    for i, chunk in enumerate(chunks):
        resposta = call_openai_api(chunk)
        logs.append(f"Chunk {i+1} processado!")

        nome_arquivo = f"{arquivo_id}_pt{i+1}.txt"
        caminho_arquivo = os.path.join(pasta_processados, nome_arquivo)

        with open(caminho_arquivo, "w", encoding="utf-8") as out_file:
            out_file.write(resposta)

        # 🔴 ADICIONANDO PRINTS PARA DEBUG
        print(f"✅ Criando ChunkProcessado para {arquivo_id} - Parte {i+1}")

        # Criando o registro no banco de dados
        novo_chunk = ChunkProcessado(
            arquivo=arquivo,
            chunk_arquivo=f"processados/{nome_arquivo}"
        )
        novo_chunk.save()

        # 🔴 CONFIRMAR SE FOI SALVO
        print(f"✅ Chunk salvo no BD: {novo_chunk.chunk_arquivo}")

    return render(request, "log.html", {"log": "\n".join(logs)})




def lista_arquivos(request):
    """ Lista os arquivos processados para download """
    arquivos = ArquivoProcessado.objects.prefetch_related("chunks").all()  # ✅ Otimiza consultas
    return render(request, "lista_arquivos.html", {"arquivos": arquivos})



def chunk_text(text, chunk_size=5000, overlap=400):
    """ Divide o texto em partes menores para processamento """
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size-overlap)]


def call_openai_api(chunk):
    """Lê o prompt de um arquivo externo e envia o texto para a OpenAI"""
    import os

    # Caminho absoluto para o arquivo de prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "../prompt_texto.txt")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_base = f.read().strip()  # tira espaços e quebras de linha extras
    except FileNotFoundError:
        prompt_base = "Corrija o texto abaixo:"

    # 🔥 Força uma quebra de linha entre o prompt e o chunk
    prompt_final = f"{prompt_base}\n\n{chunk}"

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt_final}],
        temperature=0.0
    )

    return response.choices[0].message["content"]



from django.http import StreamingHttpResponse

def sse_processamento(request, arquivo_id):
    """Gera eventos SSE para acompanhamento em tempo real."""
    from .models import ChunkProcessado
    from django.shortcuts import get_object_or_404
    import time

    def event_stream():
        yield "data: Iniciando processamento...\n\n"

        arquivo = get_object_or_404(ArquivoProcessado, id=arquivo_id)
        caminho = arquivo.arquivo_original.path

        try:
            with open(caminho, "r", encoding="utf-8") as f:
                texto = f.read()
        except FileNotFoundError:
            yield "data: Erro - Arquivo não encontrado.\n\n"
            return
        
        chunks = chunk_text(texto)
        pasta_processados = "media/processados/"
        os.makedirs(pasta_processados, exist_ok=True)

        for i, chunk in enumerate(chunks):
            yield f"data: Processando Chunk {i+1}...\n\n"
            time.sleep(0.5)  # Simula tempo de processamento

            resposta = call_openai_api(chunk)
            
            nome_arquivo = f"{arquivo_id}_pt{i+1}.txt"
            caminho_arquivo = os.path.join(pasta_processados, nome_arquivo)

            with open(caminho_arquivo, "w", encoding="utf-8") as out_file:
                out_file.write(resposta)

            # Salva no banco de dados (ERA ISSO QUE FALTAVA)
            novo_chunk = ChunkProcessado(
                arquivo=arquivo,
                chunk_arquivo=f"processados/{nome_arquivo}"
            )
            novo_chunk.save()

            yield f"data: Chunk {i+1} concluído!\n\n"

        yield "data: Processamento finalizado!\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")

def iniciar_processamento(request, arquivo_id):
    """Renderiza a página que exibe o progresso do processamento."""
    return render(request, "processamento.html", {"arquivo_id": arquivo_id})


def arquivos_processados(request, arquivo_id):
    """ Exibe os arquivos processados e seus conteúdos """
    from django.http import Http404
    from django.conf import settings

    arquivo = get_object_or_404(ArquivoProcessado, id=arquivo_id)
    chunks = ChunkProcessado.objects.filter(arquivo=arquivo)

    if not chunks.exists():
        raise Http404("Nenhum chunk foi encontrado para este arquivo.")

    arquivos = []
    for chunk in chunks:
        try:
            caminho_absoluto = chunk.chunk_arquivo.path  # Caminho real do arquivo .txt
            with open(caminho_absoluto, "r", encoding="utf-8") as f:
                conteudo = f.read()
        except Exception as e:
            conteudo = f"[Erro ao ler arquivo: {e}]"

        arquivos.append({
            "nome": os.path.basename(chunk.chunk_arquivo.name),
            "caminho": chunk.chunk_arquivo.url,
            "conteudo": conteudo.strip()  # .strip() para evitar linhas vazias no início/fim
        })

    return render(request, "arquivos_processados.html", {
        "arquivos": arquivos,
        "arquivo_id": arquivo_id
    })
