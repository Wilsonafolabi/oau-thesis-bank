import pathlib
p = pathlib.Path("src/services/aiService.ts")
s = p.read_text(encoding="utf-8")
old = "  const response = await fetch(url, init);"
new = "  init.headers = headers;\n  const response = await fetch(url, init);"
if "init.headers = headers;" not in s:
    s = s.replace(old, new)
# Point AI calls at the REAL legacy endpoints now mounted at /api/ai
s = s.replace("aiRequest<ResearchGap[] | { gaps: ResearchGap[] }>(`v1/research-gaps/${query}`)", "aiRequest<ResearchGap[] | { gaps: ResearchGap[] }>(`ai/detect-gaps${query}`)")
s = s.replace("aiRequest<Recommendation[]>(`v1/intelligence/researchers?limit=${topK}`)", "aiRequest<Recommendation[] | { recommendations: Recommendation[] }>(`ai/recommend?user_id=${encodeURIComponent(userId)}&top_k=${topK}`).then(d => Array.isArray(d) ? d : (d.recommendations || []))")
s = s.replace("aiRequest<{ nodes: unknown[]; edges: unknown[] }>('v1/intelligence/researchers')", "aiRequest<{ nodes: unknown[]; edges: unknown[] }>('ai/network')")
s = s.replace("aiRequest<{ job_id: string }>('v1/documents/upload', { method: 'POST', body: form })", "aiRequest<SimilarityReport>('ai/check-similarity', { method: 'POST', body: form })")
s = s.replace("return { status: 'processing', message: `Job ${uploadRes.job_id} queued for similarity check.` };", "return uploadRes;")
p.write_text(s, encoding="utf-8")
print("FIXED: auth headers now attached + real AI endpoints wired")
