# Document reading for messy invoices/GRs with open VLMs (Fireworks buildathon, 2026-11-02)

## Is document reading "solved" for scanned/handwritten invoices & receipts?

### Takeaway
It is close to solved for clean, digital-born page parsing (where small specialized open OCR VLMs now beat frontier models), but NOT solved for handwriting, fine-grained perception, and complex element/table parsing. OCRBench v2 authors report most LMMs score below 50/100. The "OCR is solved" claim holds only for clean pages.

### Cited Findings
- OCRBench v2 (10,000 human-verified QA pairs, 31 scenarios, plus a 1,500-image private set) found "most LMMs score below 50 (100 in total)". It names five weak areas: less frequently encountered text recognition, fine-grained perception, layout perception, complex element parsing, and logical reasoning. It explicitly calls handwritten content extraction "underexplored". — [arXiv 2501.00321](https://arxiv.org/abs/2501.00321)
- CC-OCR (39 subsets, 7,058 images, 41% from real applications, with a key information extraction track) reports weaknesses in text grounding, multi-orientation (rotated scans), and "hallucination of repetition". — [arXiv 2412.02210](https://arxiv.org/abs/2412.02210)
- The OmniDocBench leaderboard (README, last pushed 2026-10-29) uses Overall = ((1−TextEdit)×100 + TableTEDS + FormulaCDM)/3. Verified rows (Overall / TextEdit / TableTEDS):
  - PaddleOCR-VL-1.6 (0.9B): 96.34 / 0.0326 / 94.76
  - MinerU2.5-Pro (1.2B): 95.75 / 0.036 / 93.42
  - GLM-OCR (0.9B): 95.22 / 0.044 / 92.83
  - Gemini 3 Pro: 92.91 / 0.064 / 89.15
  - Gemini 3 Flash: 92.62 / 0.066 / 89.29
  - Qwen3-VL-235B: 89.78 / 0.063 / 83.07
  - GPT-5.2: 86.59 / 0.114 / 82.95
  - Top entry OXR-1.0: 97.03
  
  — [OmniDocBench README](https://github.com/opendatalab/OmniDocBench)
- OmniDocBench is a document-parsing benchmark (PDF pages to Markdown). It covers text, tables, formulas, and reading order. Handwriting and degraded scans are not its main focus. — [OmniDocBench README](https://github.com/opendatalab/OmniDocBench)

### Inferences
- On clean layout and table parsing, roughly 1B specialized OCR VLMs beat frontier general VLMs by about 3–10 Overall points. On this benchmark, "frontier = best reader" is false.
- Benchmarks still flag handwriting, rotated text, and fine-grained digits as failure modes. Those are exactly the noise sources on GR carrier notes and scanned invoices. Expect residual errors on handwritten quantities and dates, so verify critical fields.
- Repetition hallucination (CC-OCR) matters for line-item tables, because duplicated rows can create fake quantity discrepancies. Dedupe and run sum checks.

### Gaps
- I could not extract verified per-model handwriting or KIE subscores from the OCRBench v2 leaderboard (an HF Space rendered client-side). A web-search summary claimed Llama Nemotron Nano VL 8B leads with 60.2 and GPT-4o scores 46.5, but I did not verify this against the primary source, so do not cite it.
- I did not verify CC-OCR KIE per-model numbers (they are in the paper PDF tables, which I did not read).
- No dedicated handwriting-on-invoices benchmark found in the time box.

## Open VLMs on Fireworks: verified model IDs and capabilities

### Takeaway
Several open VLMs have Fireworks model pages marked "Vision (VLM)". Docs examples use `accounts/fireworks/models/kimi-k2p5` for image input. Model pages show "JSON" support for the vision models I checked. Serverless availability looked "Not Supported" on many pages, so check your own account (`firectl model get`) before you rely on serverless.

### Cited Findings
- Vision docs use `accounts/fireworks/models/kimi-k2p5` in chat-completions image examples (URL or base64 `image_url`). Limits:
  - 120 images per request
  - base64 total under 10MB
  - image URLs under 5MB and downloadable within 1.5s
  - formats: png, jpg, jpeg, gif, bmp, tiff, ppm
  - VLMs do not take PDFs natively; render pages to images (the docs show pypdfium2 at 200 DPI)
  - Llama 3.2 Vision needs images placed before text
  
  — [Fireworks Vision Models docs](https://docs.fireworks.ai/guides/querying-vision-language-models)
- The "Which model should I use?" page recommends these for "Vision & document understanding":
  - DeepSeek V4.1 Flash 1017 (`deepseek-v4p1-flash-1017`)
  - Qwen3.7 Plus (`qwen3p7-plus`)
  - Step 3.7 Flash (`step-3p7-flash-nvfp4`)
  - Gemma 4 31B (`gemma-4-31b-it`, listed as small)
  
  — [Fireworks recommended models](https://docs.fireworks.ai/guides/recommended-models)
- Model pages checked at fireworks.ai/models/fireworks/<id> on 2026-11-02:
  - All of these returned HTTP 200 and showed "Vision (VLM)" and image input: `kimi-k2p5`, `qwen3p7-plus`, `gemma-4-31b-it`, `qwen3-vl-30b-a3b-instruct`, `qwen3-vl-8b-instruct`, `qwen3-vl-235b-a22b-instruct`, `qwen2p5-vl-32b-instruct`, `llama4-maverick-instruct-basic`, `llama-v3p2-11b-vision-instruct`.
  - "Fine-tuning Supported": `kimi-k2p5`, `gemma-4-31b-it`, `qwen3-vl-30b-a3b-instruct`.
  - "Fine-tuning Not Supported": `qwen3p7-plus`, `qwen3-vl-8b-instruct`, `qwen2p5-vl-32b-instruct`.
  - "JSON" appeared on most pages. `qwen2p5-vl-32b-instruct` and `qwen3-vl-8b-instruct` show "Function Calling Not Supported".
  - `deepseek-v4p1-flash-1017` returned 404 at that public URL; it is linked only via app.fireworks.ai.
  
  — e.g. [kimi-k2p5](https://fireworks.ai/models/fireworks/kimi-k2p5), [qwen3-vl-30b-a3b-instruct](https://fireworks.ai/models/fireworks/qwen3-vl-30b-a3b-instruct), [gemma-4-31b-it](https://fireworks.ai/models/fireworks/gemma-4-31b-it)
- Structured outputs docs describe JSON-schema and grammar modes generally. They do not single out vision models. — [Fireworks Structured Outputs](https://docs.fireworks.ai/structured-responses/structured-response-formatting)

### Inferences
- Likely best open readers on Fireworks: `qwen3-vl-30b-a3b-instruct` (vision, tunable) and `kimi-k2p5` (vision, tunable, used in the docs). `gemma-4-31b-it` is a small, tunable fallback.
- JSON schema with image input is plausible because model pages advertise JSON, but run a one-call smoke test with `response_format` on the chosen model first.

### Gaps
- The model-page scrape showed "Serverless Not Supported" even for `kimi-k2p5`, yet the docs use kimi-k2p5 in what looks like a serverless example. This is likely a page-parse ambiguity. Confirm with `firectl model get -a fireworks <id>` or a live call. Catalog listing does not prove account access.
- No Fireworks page states explicitly that JSON-schema `response_format` is supported together with image inputs.
- No specialized OCR VLMs (PaddleOCR-VL, MinerU, GLM-OCR, dots.ocr) were found in the Fireworks catalog in this check. I did not search exhaustively.

## Cheap best practices to reduce reading errors

### Takeaway
No source in the time box quantified these techniques for invoices. Recommendations are inferred from the benchmark failure modes above: repetition hallucination, multi-orientation, fine-grained digits, and handwriting.

### Cited Findings
- Known LMM OCR failure modes are grounding, multi-orientation, and repetition hallucination ([CC-OCR](https://arxiv.org/abs/2412.02210)), plus fine-grained perception and complex element parsing ([OCRBench v2](https://arxiv.org/abs/2501.00321)).
- Specialized small OCR VLMs lead page parsing on [OmniDocBench](https://github.com/opendatalab/OmniDocBench). This supports a two-pass design: a specialized OCR/markdown pass, then a VLM or LLM pass for extraction.
- Fireworks image constraints: downsize images to save tokens, put static instructions first for prompt caching (text and images can be cached), and render PDFs to page images. — [Fireworks Vision docs](https://docs.fireworks.ai/guides/querying-vision-language-models)

### Inferences (recommended pipeline; not benchmark-verified)
1. Deskew/rotate before reading, because multi-orientation is a known weakness.
2. Pass 1: a full-page VLM extraction to a strict JSON schema. Every field is `{value, confidence, status: ok|unreadable|absent}`, and the prompt forbids guessing.
3. Deterministic checks:
   - the sum of line amounts equals the subtotal; subtotal + tax = total
   - qty × unit price = line amount
   - PO number and vendor match across the PO, invoice, and GR
   - dedupe repeated line rows
4. Re-read only fields that fail a check or are flagged low-confidence or handwritten. Crop the region or re-prompt with the field name and the candidate values from the other two documents. Use k=3 self-consistency on those fields only, and accept a value only by majority.
5. Escalate a case only when a critical field stays inconsistent after the re-read. If every disagreement is explained by "unreadable" fields, label it "document-quality" rather than a real discrepancy. This directly targets the team's "document-only escalation" hypothesis.

### Gaps
- No primary source found quantifying the gains from field-level re-reading or self-consistency for document KIE.

## Synthetic noisy document generation (cheap and legal)

### Takeaway
Augraphy (MIT) is the main tool for scan, fax, and copy degradation. TRDG (MIT) renders text lines with arbitrary fonts, including handwriting fonts. Render clean invoices, POs, and GRs from templates you control, then degrade them.

### Cited Findings
- `sparkfish/augraphy`, MIT license: "Augmentation pipeline for rendering synthetic paper printing, faxing, scanning and copy machine processes". Last pushed 2025-07-20. — [GitHub](https://github.com/sparkfish/augraphy)
- `Belval/TextRecognitionDataGenerator`, MIT license: synthetic text-image generator (fonts, blur, skew, backgrounds). — [GitHub](https://github.com/Belval/TextRecognitionDataGenerator)
- OmniDocBench is Apache-2.0, and AlibabaResearch/AdvancedLiterateMachinery (home of CC-OCR) is Apache-2.0. Both are usable for evaluation reference. — [OmniDocBench](https://github.com/opendatalab/OmniDocBench), [ALM](https://github.com/AlibabaResearch/AdvancedLiterateMachinery)

### Inferences
- Recipe:
  1. Build HTML or ReportLab templates for PO, invoice, and GR from your own synthetic data.
  2. Render to PNG.
  3. Overlay handwritten GR notes ("rec'd 9/10 short 2", initials, "damaged box") using open-licensed handwriting fonts (check each font's OFL/Apache license, e.g. on Google Fonts), plus a rotated, semi-transparent stamp PNG.
  4. Apply an Augraphy pipeline: ink bleed, dirty drum, low-ink lines, folds, JPEG/fax noise, small rotation, blur.
- Keep ground truth from the template and inject controlled "document-only" noise, for example the same quantity written as "1O" vs "10", or a comma vs period decimal. This yields labeled false-positive cases.

### Gaps
- I did not verify DocCreator's license or availability in this time box. I also did not verify licenses for specific handwriting fonts.

## Fine-tuning a VLM for key-field extraction on Fireworks

### Takeaway
Feasible. Fireworks docs describe vision SFT using the same messages JSONL with base64 `image_url` parts on user turns. Model pages show "Fine-tuning Supported" for `qwen3-vl-30b-a3b-instruct`, `kimi-k2p5`, and `gemma-4-31b-it`. Trained LoRAs are served via on-demand (dedicated) deployments, which costs time and money for a same-day hackathon. Evidence that small fine-tuned models beat large general ones is strong for page parsing on OmniDocBench and anecdotal for invoice KIE.

### Cited Findings
- Fireworks SFT:
  - The dataset is JSONL, 3 to 3M lines, in OpenAI chat format.
  - Vision training puts image parts on `user` messages as `data:image/<type>;base64,...`; system and assistant messages cannot contain images.
  - Check tunability with `firectl model get -a fireworks <MODEL-ID>` and look for `Tunable: true`.
  - Launch with `firectl sftj create --base-model ... --dataset ... --output-model ...`.
  - An on-demand (dedicated) deployment is "the only supported method for serving trained models".
  
  — [Fireworks SFT docs](https://docs.fireworks.ai/fine-tuning/fine-tuning-models)
- The fine-tuning Models page says vision support is "model- and surface-specific" and notes "Muse Glimmer 30B SFT is free to train until November 30, 2026". I did not verify whether Muse Glimmer is a vision model. — [Fireworks fine-tuning models](https://docs.fireworks.ai/fine-tuning/models)
- On OmniDocBench, 0.9–1.2B specialized models (PaddleOCR-VL-1.6 96.34, MinerU2.5-Pro 95.75) beat Gemini 3 Pro (92.91), GPT-5.2 (86.59), and Qwen3-VL-235B (89.78). — [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
- VirtusLab case study (vendor blog):
  - Qwen3-VL-2B-Instruct with LoRA (r=4, alpha=8), trained 3 epochs on about 1.6k samples from `katanaml-org/invoices-donut-data-v1`.
  - Extracts 3 keys (subtotal, tax, total) and is compared with GPT-4o-mini and GPT-5.2.
  - Evaluated on only 62 samples.
  - Notes GPT-4o-mini can use 20x+ more image tokens than GPT-5.
  
  — [VirtusLab](https://virtuslab.com/blog/ai/sft-scaling-small-vision-language-models)

### Inferences
- For a same-day build, prefer prompt and verification engineering on a serverless or already-available VLM. Treat fine-tuning as a stretch goal: a LoRA on `qwen3-vl-30b-a3b-instruct` with a few hundred synthetic examples. It requires a dedicated deployment to serve.
- The tax-form-style focus on company-specific key fields is supported. Narrow, schema-specific extraction is where specialized or fine-tuned small models win, but the evidence for invoice KIE specifically is thin.

### Gaps
- I could not read VirtusLab's accuracy numbers (they are in a figure). With 62 eval samples, the evidence is weak.
- I did not verify Fireworks training cost or turnaround time for a VLM SFT job, or whether serverless LoRA serving exists for VLMs.
