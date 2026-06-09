import re
import unicodedata
from pathlib import Path

try:
    import ftfy
except ImportError:
    ftfy = None

try:
    from kiwipiepy import Kiwi
except ImportError:
    Kiwi = None


def refine_text(input_path: Path, output_dir: Path, is_scan: bool = False):
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # =========================================================================
    # 1단계: 노이즈 제거 및 기초 정제
    # =========================================================================
    if ftfy:
        text = ftfy.fix_text(text)
    text = unicodedata.normalize('NFC', text)

    text = re.sub(r'<!--\s*PageBreak\s*-->', '\n\n', text)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'[ \t]+', ' ', text)

    (output_dir / "step1_clean.txt").write_text(text, encoding='utf-8')

    # =========================================================================
    # 2단계: 끊긴 문장 병합
    # =========================================================================
    skip_merge_pattern = re.compile(r'^(\s*#|\s*\*|\s*-|\s*>|\|)')
    end_pattern = re.compile(r'(다|요|까|\.|\?|!|:)\s*$')

    lines = text.split('\n')
    merged_lines = []
    current_line = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_line:
                merged_lines.append(current_line)
                current_line = ""
            merged_lines.append("")
            continue

        if skip_merge_pattern.match(stripped):
            if current_line:
                merged_lines.append(current_line)
                current_line = ""
            merged_lines.append(stripped)
            continue

        current_line = (current_line + " " + stripped) if current_line else stripped

        if end_pattern.search(current_line):
            merged_lines.append(current_line)
            current_line = ""

    if current_line:
        merged_lines.append(current_line)

    merged_text = re.sub(r'\n{3,}', '\n\n', '\n'.join(merged_lines))
    (output_dir / "step2_merged.txt").write_text(merged_text, encoding='utf-8')

    # =========================================================================
    # 3단계: Kiwi 문장 분리
    # =========================================================================
    if not Kiwi:
        print("  - [주의] kiwipiepy가 없어 3·4단계를 건너뜁니다.")
        return

    kiwi = Kiwi()
    sentences = []
    for paragraph in merged_text.split('\n'):
        if not paragraph.strip():
            sentences.append("")
            continue
        if re.match(r'^(#|\|)', paragraph.strip()):
            sentences.append(paragraph.strip())
        else:
            for s in kiwi.split_into_sents(paragraph):
                sentences.append(s.text)

    step3_text = '\n'.join(sentences)
    (output_dir / "step3_kiwi_sents.txt").write_text(step3_text, encoding='utf-8')

    # =========================================================================
    # 4단계: 띄어쓰기 교정 (Kiwi space) — 스캔 PDF만 적용
    # =========================================================================
    if not is_scan:
        print("  - [4단계 생략] digital PDF는 띄어쓰기 교정 불필요")
        return

    spaced = []
    for s in sentences:
        if not s.strip() or re.match(r'^(#|\|)', s.strip()):
            spaced.append(s)
        elif len(s) > 5:
            spaced.append(kiwi.space(s, reset_whitespace=True))
        else:
            spaced.append(s)

    (output_dir / "step4_spaced.txt").write_text('\n'.join(spaced), encoding='utf-8')


def main():
    base_dir = Path(r"c:\Users\USER\ms-project3\preprocess\extract\content-understanding")
    out_base = Path(__file__).parent / "result-v2"

    targets = [
        (base_dir / "result-digital" / "txt", "result-digital", False),
        (base_dir / "result-scan"    / "txt", "result-scan",    True),
    ]

    for target_dir, label, is_scan in targets:
        md_file = target_dir / "content.txt"
        if not md_file.exists():
            print(f"\n[오류] {md_file} 없음")
            continue

        output_dir = out_base / label
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n▶ [{label}] 정제 시작 (scan={is_scan})...")
        refine_text(md_file, output_dir, is_scan=is_scan)
        print(f"▶ [{label}] 완료 → {output_dir}")


if __name__ == "__main__":
    main()
