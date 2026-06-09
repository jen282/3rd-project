import os
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

try:
    from pykospacing import Spacing
except ImportError:
    Spacing = None


def refine_markdown(input_path: Path, output_dir: Path):
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # =========================================================================
    # 1단계: 1차 노이즈 제거 (HTML/주석 제거 및 기초 정제)
    # =========================================================================
    if ftfy:
        text = ftfy.fix_text(text)
    text = unicodedata.normalize('NFC', text)

    # PageBreak는 문단 구분을 위해 개행으로 남겨둠
    text = re.sub(r'<!--\s*PageBreak\s*-->', '\n\n', text)
    # 나머지 주석 제거 (PageHeader, PageFooter, PageNumber 등)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    
    # <figure>, <caption>, <table> 등 HTML 태그 제거 (내부 텍스트는 유지되도록 태그 자체만 삭제)
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # URL 및 이메일 제거
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', '', text)
    
    # 불필요한 연속 공백 및 탭 정리
    text = re.sub(r'[ \t]+', ' ', text)
    
    step1_out = output_dir / "step1_clean.txt"
    with open(step1_out, 'w', encoding='utf-8') as f:
        f.write(text)


    # =========================================================================
    # 2단계: 텍스트 병합 (정규표현식) - 끊긴 문장 강제 병합
    # =========================================================================
    lines = text.split('\n')
    merged_lines = []
    current_line = ""
    
    # 헤딩, 리스트 기호, 테이블 바 등은 병합 예외 처리
    skip_merge_pattern = re.compile(r'^(\s*#|\s*\*|\s*-|\s*>|\|)')
    # 문장 종결을 나타내는 패턴 (다, 요, 까, 마침표, 물음표, 느낌표, 콜론 등)
    end_pattern = re.compile(r'(다|요|까|\.|\?|!|:)\s*$')
    
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
            
        if current_line:
            current_line += " " + stripped
        else:
            current_line = stripped
            
        if end_pattern.search(current_line):
            merged_lines.append(current_line)
            current_line = ""
            
    if current_line:
        merged_lines.append(current_line)
        
    merged_text = '\n'.join(merged_lines)
    # 과도한 연속 줄바꿈 축소
    merged_text = re.sub(r'\n{3,}', '\n\n', merged_text)
    
    step2_out = output_dir / "step2_merged.txt"
    with open(step2_out, 'w', encoding='utf-8') as f:
        f.write(merged_text)


    # =========================================================================
    # 3단계: 정교한 문장 단위 분리 및 구조화 (kiwipiepy)
    # =========================================================================
    sentences = []
    if Kiwi:
        kiwi = Kiwi()
        for paragraph in merged_text.split('\n'):
            if not paragraph.strip():
                sentences.append("")
                continue
            
            if re.match(r'^(#|\|)', paragraph.strip()):
                sentences.append(paragraph.strip())
            else:
                sents = kiwi.split_into_sents(paragraph)
                for s in sents:
                    sentences.append(s.text)
                    
        step3_text = '\n'.join(sentences)
        step3_out = output_dir / "step3_kiwi_sents.txt"
        with open(step3_out, 'w', encoding='utf-8') as f:
            f.write(step3_text)
    else:
        print("  - [주의] kiwipiepy가 설치되어 있지 않아 3단계를 건너뜁니다.")
        sentences = merged_text.split('\n')
        step3_text = merged_text


    # =========================================================================
    # 4단계: 띄어쓰기 오류 정밀 교정 (PyKoSpacing)
    # =========================================================================
    if Spacing and Kiwi:
        spacing = Spacing()
        spaced_sentences = []
        for s in sentences:
            if not s.strip() or re.match(r'^(#|\|)', s.strip()):
                spaced_sentences.append(s)
            else:
                if len(s) > 5:
                    spaced_sentences.append(spacing(s))
                else:
                    spaced_sentences.append(s)
                    
        step4_text = '\n'.join(spaced_sentences)
        step4_out = output_dir / "step4_spaced.txt"
        with open(step4_out, 'w', encoding='utf-8') as f:
            f.write(step4_text)
    else:
        if not Spacing:
            print("  - [주의] pykospacing이 설치되어 있지 않아 4단계를 건너뜁니다.")
            print("    (설치 팁: pip install git+https://github.com/haven-jeon/PyKoSpacing.git)")


def main():
    base_dir = Path(r"c:\Users\USER\ms-project3\preprocess\extract\content-understanding")
    script_dir = Path(__file__).parent

    targets = [
        (base_dir / "result-digital" / "txt", "result-digital"),
        (base_dir / "result-scan"    / "txt", "result-scan"),
    ]

    for target_dir, label in targets:
        md_file = target_dir / "content.txt"
        if not md_file.exists():
            print(f"\n[오류] {md_file} 없음")
            continue

        output_dir = script_dir / label
        output_dir.mkdir(exist_ok=True)

        print(f"\n▶ [{label}] 문서 정제 파이프라인 시작...")
        refine_markdown(md_file, output_dir)
        print(f"▶ [{label}] 완료 → {output_dir}")

if __name__ == "__main__":
    main()