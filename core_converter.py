import os
import sys
import json
import shutil
import subprocess

def get_audio_info(file_path):
    """
    ffprobe를 사용하여 오디오 파일 정보(codec_name, bit_rate, sample_rate, bit_depth, channels, format_label)를 추출.
    실패 시 None 반환.
    """
    # Windows에서 subprocess 창 팝업 방지
    creation_flags = 0
    if sys.platform == 'win32':
        creation_flags = subprocess.CREATE_NO_WINDOW

    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,bit_rate,sample_rate,bits_per_raw_sample,sample_fmt,channels',
            '-of', 'json',
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, creationflags=creation_flags)
        data = json.loads(result.stdout)
        
        if 'streams' in data and len(data['streams']) > 0:
            stream = data['streams'][0]
            
            codec_name = stream.get('codec_name', '').lower()
            sample_rate = int(stream.get('sample_rate', 0)) if stream.get('sample_rate') else 0
            bit_rate = int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else 0
            channels = int(stream.get('channels', 2)) if stream.get('channels') else 2
            
            # 비트뎁스 판별
            bits_per_raw = stream.get('bits_per_raw_sample')
            if bits_per_raw and bits_per_raw.isdigit():
                bit_depth = int(bits_per_raw)
            else:
                # sample_fmt로 유추
                fmt = stream.get('sample_fmt', '')
                if 's32' in fmt or 'flt' in fmt or 'dbl' in fmt:
                    bit_depth = 24
                elif 's16' in fmt:
                    bit_depth = 16
                else:
                    bit_depth = 16  # 기본값
            
            # DSD 파일 판별 및 명칭 생성
            dsd_rate = ""
            if 'dsd' in codec_name:
                if sample_rate >= 11289600:
                    dsd_rate = "DSD256"
                elif sample_rate >= 5644800:
                    dsd_rate = "DSD128"
                elif sample_rate >= 2822400:
                    dsd_rate = "DSD64"
                else:
                    dsd_rate = "DSD"
                    
            format_label = dsd_rate if dsd_rate else codec_name.upper()
            
            return {
                'codec_name': codec_name,
                'sample_rate': sample_rate,
                'bit_rate': bit_rate,
                'bit_depth': bit_depth,
                'channels': channels,
                'dsd_rate': dsd_rate,
                'format_label': format_label
            }
    except Exception as e:
        print(f"ffprobe 에러 ({file_path}): {e}", file=sys.stderr)
    return None

def is_lossless(codec_name):
    """
    무손실 오디오 코덱인지 여부 판별.
    """
    lossless_codecs = ['flac', 'alac', 'ape', 'wav', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'dsd_lsbf', 'dsd_msbf']
    # 'dsd' 텍스트 포함 및 pcm 계열 무손실 판단
    if any(lc in codec_name for lc in lossless_codecs) or 'dsd' in codec_name or 'pcm' in codec_name:
        return True
    return False

def should_encode(src_info, target_format, target_setting):
    """
    원본 스펙과 유저 타겟 설정을 비교하여 인코딩을 진행할지(True), 단순 복사할지(False) 판별.
    target_format: 'MP3', 'FLAC', 'WAV', 'M4A', 'OGG'
    target_setting: 
      - 손실포맷(MP3/M4A/OGG): target_bitrate (int, 예: 192)
      - 무손실포맷(FLAC/WAV): (bit_depth, sample_rate) (tuple, 예: (24, 96000))
    """
    if src_info is None:
        return True  # 정보 조회 실패 시 일단 인코딩 시도
        
    src_codec = src_info['codec_name']
    src_is_dsd = bool(src_info['dsd_rate'])
    src_is_lossless = is_lossless(src_codec)
    
    tgt_is_lossless = target_format in ['WAV', 'FLAC']
    
    # 1. DSD 원본인 경우 -> 항상 인코딩 (타겟 포맷으로 변환)
    if src_is_dsd:
        return True
        
    # 2. 무손실 원본 (WAV, FLAC, APE 등)인 경우
    if src_is_lossless:
        if not tgt_is_lossless:
            # 무손실 -> 손실 포맷 변환: 항상 인코딩 진행
            return True
        else:
            # 무손실 -> 무손실 포맷 변환: 품질 비교 (비트뎁스 * 샘플레이트)
            src_quality = src_info['sample_rate'] * src_info['bit_depth']
            tgt_bit_depth, tgt_sample_rate = target_setting
            tgt_quality = tgt_sample_rate * tgt_bit_depth
            
            # 목표 품질이 원본보다 낮을 때만 실제 변환(인코딩) 수행
            return tgt_quality < src_quality
            
    # 3. 손실 원본 (MP3, M4A, OGG 등)인 경우
    else:
        if tgt_is_lossless:
            # 손실 -> 무손실 포맷 변환: 음질 향상 불가하므로 인코딩 생략 (단순 복사)
            return False
        else:
            # 손실 -> 손실 포맷 변환: 비트레이트 비교
            # 원본 비트레이트가 0이면 ffprobe가 감지하지 못한 것이므로 일단 변환 수행
            if src_info['bit_rate'] == 0:
                return True
                
            src_bitrate_kbps = src_info['bit_rate'] / 1000
            tgt_bitrate_kbps = target_setting
            
            # 목표 비트레이트가 원본 비트레이트보다 낮을 때만 인코딩 수행
            return tgt_bitrate_kbps < src_bitrate_kbps

def resolve_output_path(file_path, output_dir, name_option, value="", target_ext=".mp3"):
    """
    원본 파일 경로와 파일명 처리 규칙, 저장 폴더, 타겟 확장자를 기준으로 최종 저장 경로를 반환.
    """
    # 1. 아웃풋 디렉토리 결정
    src_dir = os.path.dirname(os.path.abspath(file_path))
    if not output_dir:
        dest_dir = src_dir
    else:
        dest_dir = os.path.abspath(output_dir)

    # 2. 파일명 결정
    filename = os.path.basename(file_path)
    name, _ = os.path.splitext(filename)

    if name_option == 'suffix':
        new_filename = f"{name}{value}{target_ext}"
    elif name_option == 'prefix':
        new_filename = f"{value}{name}{target_ext}"
    else: # 'overwrite'
        new_filename = f"{name}{target_ext}"

    dest_path = os.path.join(dest_dir, new_filename)
    return dest_path

def process_audio(file_path, target_format, target_setting, output_dir, name_option, value=""):
    """
    오디오 파일 변환/복사 실행 코어 로직.
    target_format: 'MP3', 'FLAC', 'WAV', 'M4A', 'OGG'
    target_setting:
      - 손실포맷: bitrate (int, 예: 192)
      - 무손실포맷: (bit_depth, sample_rate) (tuple, 예: (24, 96000))
    """
    if not os.path.exists(file_path):
        return 'FAIL', "파일이 존재하지 않습니다."
        
    src_info = get_audio_info(file_path)
    if src_info is None:
        return 'FAIL', "오디오 파일 정보를 분석할 수 없습니다."
        
    # 확장자 매핑
    ext_map = {
        'MP3': '.mp3',
        'FLAC': '.flac',
        'WAV': '.wav',
        'M4A': '.m4a',
        'OGG': '.ogg'
    }
    target_ext = ext_map.get(target_format, '.mp3')
    
    # 3. 아웃풋 경로 결정
    dest_path = resolve_output_path(file_path, output_dir, name_option, value, target_ext)
    
    # 저장 폴더 자동 생성
    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        
    is_same_file = (os.path.abspath(file_path) == os.path.abspath(dest_path))
    
    # 인코딩 실행 여부 판단
    need_encode = should_encode(src_info, target_format, target_setting)
    
    # Windows에서 subprocess 창 팝업 방지
    creation_flags = 0
    if sys.platform == 'win32':
        creation_flags = subprocess.CREATE_NO_WINDOW
        
    # 정보 텍스트 생성
    src_label = src_info['format_label']
    if 'DSD' in src_label:
        src_spec = src_label
    elif is_lossless(src_info['codec_name']):
        src_spec = f"{src_info['bit_depth']}bit/{int(src_info['sample_rate']/1000)}k"
    else:
        src_spec = f"{int(src_info['bit_rate']/1000)}k"
        
    if target_format in ['FLAC', 'WAV']:
        tgt_spec = f"{target_setting[0]}bit/{int(target_setting[1]/1000)}k"
    else:
        tgt_spec = f"{target_setting}k"

    if need_encode:
        try:
            # ffmpeg 기본 인수 구성
            cmd = ['ffmpeg', '-y', '-i', file_path]
            
            # 포맷별 인코더/파라미터 분기
            if target_format == 'WAV':
                codec = 'pcm_s24le' if target_setting[0] == 24 else 'pcm_s16le'
                cmd += ['-codec:a', codec, '-ar', str(target_setting[1])]
            elif target_format == 'FLAC':
                sample_fmt = 's32' if target_setting[0] == 24 else 's16'
                cmd += ['-codec:a', 'flac', '-sample_fmt', sample_fmt, '-ar', str(target_setting[1])]
            elif target_format == 'MP3':
                cmd += ['-codec:a', 'libmp3lame', '-b:a', f"{target_setting}k"]
            elif target_format == 'M4A':
                cmd += ['-codec:a', 'aac', '-b:a', f"{target_setting}k"]
            elif target_format == 'OGG':
                cmd += ['-codec:a', 'libvorbis', '-b:a', f"{target_setting}k"]
                
            cmd.append(dest_path)
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
            return 'SUCCESS', f"[{src_label}] {src_spec} -> [{target_format}] {tgt_spec} 변환 완료"
            
        except subprocess.CalledProcessError as e:
            return 'FAIL', f"FFmpeg 에러: {e.stderr.decode('utf-8', errors='ignore')}"
        except Exception as e:
            return 'FAIL', f"변환 에러: {e}"
    else:
        # 동일 경로 덮어쓰기이면서 스펙도 하향이 아닐 때는 생략
        if is_same_file:
            return 'SKIP', f"변환 불필요 (원본 {src_spec} <= 목표 {tgt_spec}, 파일 보존)"
            
        try:
            # 원본 코덱 그대로 복사 (단, 확장자가 다르면 단순 파일 복사가 아닌 ffmpeg 오디오 스트림 카피 적용 가능)
            src_ext = os.path.splitext(file_path)[1].lower()
            if src_ext == target_ext.lower():
                # 확장자가 같으면 완전히 단순 복사
                shutil.copy2(file_path, dest_path)
            else:
                # 확장자가 다르면 ffmpeg stream copy 적용 (인코딩 없이 컨테이너 변경)
                copy_cmd = ['ffmpeg', '-y', '-i', file_path, '-c:a', 'copy', dest_path]
                subprocess.run(copy_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                
            return 'COPY', f"단순 복사 (원본 {src_spec} <= 목표 {tgt_spec}, 음질 유지)"
        except Exception as e:
            return 'FAIL', f"복사 에러: {e}"

if __name__ == '__main__':
    # 간단한 CLI 테스트 모드
    if len(sys.argv) < 4:
        print("사용법 (손실): python core_converter.py <file> MP3/M4A/OGG <bitrate_kbps>")
        print("사용법 (무손실): python core_converter.py <file> WAV/FLAC <bit_depth> <sample_rate_hz>")
        sys.exit(1)
        
    in_file = sys.argv[1]
    tgt_fmt = sys.argv[2].upper()
    
    if tgt_fmt in ['WAV', 'FLAC']:
        depth = int(sys.argv[3])
        s_rate = int(sys.argv[4])
        setting = (depth, s_rate)
    else:
        setting = int(sys.argv[3])
        
    print(f"인풋 파일: {in_file}")
    print(f"타겟 설정: {tgt_fmt} / {setting}")
    
    status, msg = process_audio(in_file, tgt_fmt, setting, "", "suffix", "_converted")
    print(f"결과: [{status}] {msg}")
