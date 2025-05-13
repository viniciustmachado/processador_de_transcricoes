import os
import re
import time
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404

import openai
import nltk
from dotenv import load_dotenv

from .models import ArquivoProcessado, ChunkProcessado

# Carrega .env e chaves
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Diretórios
BASE_DIR = Path(settings.BASE_DIR)
MEDIA_DIR = Path(settings.MEDIA_ROOT)
PROCESSADOS_DIR = MEDIA_DIR / "processados"

# Recursos lazy
nlp = enc = tiler = None

def load_prompt() -> str:
    prompt_file = BASE_DIR / "prompt_texto.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return "Corrija o texto abaixo:"

def init_resources():
    global nlp, enc, tiler
    if nlp is None:
        import spacy
        nlp = spacy.load("pt_core_news_sm")
    if enc is None:
        from tiktoken import encoding_for_model
        enc = encoding_for_model("gpt-4o-mini")
    if tiler is None:
        from nltk.tokenize import TextTilingTokenizer
        for pkg in ("punkt", "stopwords"):
            subdir = "tokenizers" if pkg=="punkt" else "corpora"
            try:
                nltk.data.find(f"{subdir}/{pkg}")
            except LookupError:
                nltk.download(pkg)
        tiler = TextTilingTokenizer(w=30, k=15)
    return nlp, enc, tiler

def strip_comments(text: str) -> str:
    # remove prefixo antes de '---' nos 300 primeiros chars
    pre = text[:300]
    i = pre.find('---')
    if i != -1:
        text = text[i+3:]
    # remove sufixo após o último '---' nos 300 últimos chars
    suf = text[-300:]
    j = suf.rfind('---')
    if j != -1:
        text = text[:-300] + suf[:j]
    return text.strip()

def normalize_transcript(text: str) -> str:
    text = re.sub(r"\b\d{1,3}:\d{2}\b", "", text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return " ".join(lines)

def chunk_text(text: str, max_tokens: int = 2000) -> list[str]:
    nlp_obj, enc_obj, _ = init_resources()
    sentences = [s.text.strip() for s in nlp_obj(text).sents]
    chunks, cur, cnt = [], [], 0
    for s in sentences:
        size = len(enc_obj.encode(s))
        if cnt + size > max_tokens:
            chunks.append(" ".join(cur).strip())
            cur, cnt = [s], size
        else:
            cur.append(s)
            cnt += size
    if cur:
        chunks.append(" ".join(cur).strip())
    return chunks

def smart_chunk(text: str, max_tokens: int = 2000) -> list[str]:
    _, enc_obj, tiler_obj = init_resources()
    clean = normalize_transcript(text)
    try:
        tiles = tiler_obj.tokenize(clean)
    except ValueError:
        tiles = [clean]
    out = []
    for t in tiles:
        if len(enc_obj.encode(t)) <= max_tokens:
            out.append(t)
        else:
            out.extend(chunk_text(t, max_tokens))
    return out

def call_openai_api(chunk: str) -> str:
    prompt = load_prompt()
    payload = f"{prompt}\n\n<texto>{chunk}</texto>"
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":payload}],
            temperature=0.0
        )
        return res.choices[0].message["content"]
    except Exception as e:
        return f"[Erro OpenAI: {e}]"

def call_groq_api(chunk: str) -> str:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        return "[Erro Groq: instale o pacote groq]"
    prompt = load_prompt()
    payload = f"{prompt}\n\n<texto>{chunk}</texto>"
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":payload}],
            temperature=0.0
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"[Erro Groq: {e}]"

def call_model_api(request, chunk: str) -> str:
    prov = request.session.get("llm_provider","openai")
    return call_groq_api(chunk) if prov=="groq" else call_openai_api(chunk)

# Views

def upload_arquivo(request):
    if request.method=="POST":
        prov = request.POST.get("provider","openai")
        request.session["llm_provider"] = prov
        arq = request.FILES.get("arquivo")
        if arq:
            novo = ArquivoProcessado(arquivo_original=arq)
            novo.save()
            return redirect("iniciar_processamento", arquivo_id=novo.id)
    return render(request, "upload.html")

def iniciar_processamento(request, arquivo_id):
    return render(request, "processamento.html", {"arquivo_id":arquivo_id})

def sse_processamento(request, arquivo_id):
    """
    Stream SSE que:
      - salva chunk original e chunk GPT
      - registra apenas GPT no DB
      - gera all.txt e zip no final
    """
    def stream():
        start = time.time()
        yield f"data: Iniciando processamento!  (0s)\n\n"

        arq = get_object_or_404(ArquivoProcessado, id=arquivo_id)
        texto = Path(arq.arquivo_original.path).read_text(encoding="utf-8")
        chunks = smart_chunk(texto)
        PROCESSADOS_DIR.mkdir(exist_ok=True, parents=True)

        _, enc_obj, _ = init_resources()
        times = []

        for idx, chunk in enumerate(chunks, 1):
            elapsed = int(time.time() - start)
            yield f"data: 🔍 Chunk {idx}: {len(enc_obj.encode(chunk))} tokens  ({elapsed}s)\n\n"
            yield f"data: ⌛ Processando Chunk {idx}...  ({elapsed}s)\n\n"

            # salva original
            orig_name = f"{arquivo_id}_pt{idx}.txt"
            orig_path = PROCESSADOS_DIR / orig_name
            orig_path.write_text(chunk, encoding="utf-8")

            # processa
            t0 = time.time()
            raw = call_model_api(request, chunk)
            proc = strip_comments(raw)
            dt = int(time.time() - t0)
            times.append(dt)

            # salva GPT
            gpt_name = f"{arquivo_id}_pt{idx}_gpt.txt"
            gpt_path = PROCESSADOS_DIR / gpt_name
            gpt_path.write_text(proc, encoding="utf-8")

            # registra apenas GPT
            ChunkProcessado.objects.create(
                arquivo=arq,
                chunk_arquivo=f"processados/{gpt_name}"
            )

            elapsed = int(time.time() - start)
            yield f"data: ✔ Chunk {idx} concluído em {dt}s  ({elapsed}s)\n\n"

        # cria all.txt
        qs = ChunkProcessado.objects.filter(arquivo=arq).order_by("id")
        all_txt = MEDIA_DIR / f"{arquivo_id}_all.txt"
        with all_txt.open("w", encoding="utf-8") as out:
            for i, cp in enumerate(qs, 1):
                part = (MEDIA_DIR / cp.chunk_arquivo.name).read_text(encoding="utf-8")
                out.write(part)
                if i < qs.count():
                    out.write("\n\n\n")

        # cria ZIP
        zip_path = MEDIA_DIR / f"{arquivo_id}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for cp in qs:
                file = MEDIA_DIR / cp.chunk_arquivo.name
                zf.write(file, arcname=file.name)

        # relatório final
        total = int(time.time() - start)
        yield f"data: **Processamento finalizado!**  ({total}s)\n\n"
        yield "data: --- relatório ---\n\n"
        for i, t in enumerate(times, 1):
            yield f"data: • Chunk {i}: {t}s\n\n"
        yield f"data: • Tempo total: {total}s\n\n"

    return StreamingHttpResponse(stream(), content_type="text/event-stream")

def arquivos_processados(request, arquivo_id):
    arq = get_object_or_404(ArquivoProcessado, id=arquivo_id)
    qs = ChunkProcessado.objects.filter(arquivo=arq).order_by("id")
    if not qs.exists():
        raise Http404("Nenhum chunk processado.")
    arquivos = []
    for cp in qs:
        conteúdo = (MEDIA_DIR / cp.chunk_arquivo.name).read_text(encoding="utf-8")
        arquivos.append({"nome": cp.chunk_arquivo.name, "conteudo": conteúdo})
    return render(request, "arquivos_processados.html", {
        "arquivos": arquivos,
        "arquivo_id": arquivo_id
    })

def download_all_text(request, arquivo_id):
    path = MEDIA_DIR / f"{arquivo_id}_all.txt"
    if not path.exists():
        raise Http404
    return FileResponse(open(path, "rb"),
                        as_attachment=True,
                        filename=path.name)

def download_zip(request, arquivo_id):
    path = MEDIA_DIR / f"{arquivo_id}.zip"
    if not path.exists():
        raise Http404
    return FileResponse(open(path, "rb"),
                        as_attachment=True,
                        filename=path.name)
