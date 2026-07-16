import os
import re
import sys
import queue
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# core_converter에서 핵심 로직 임포트
from core_converter import get_audio_info, process_audio, should_encode, resolve_output_path, is_lossless

# 드래그 앤 드롭 라이브러리 예외 처리 로딩
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception as e:
    print(f"TkinterDnD2 로드 실패: {e}")
    HAS_DND = False

# 시스템 인코딩 및 테마 설정
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 지원하는 오디오 확장자 리스트
SUPPORTED_EXTENSIONS = ('.mp3', '.m4a', '.ogg', '.flac', '.wav', '.ape', '.dsf', '.dff')

def parse_dropped_files(dropped_str):
    """
    tkinterdnd2 드롭 데이터를 파싱하여 개별 파일/폴더 경로 리스트를 반환.
    """
    braced_paths = re.findall(r'\{(.*?)\}', dropped_str)
    cleaned_str = re.sub(r'\{.*?\}', ' ', dropped_str)
    
    files = [p.strip() for p in braced_paths if p.strip()]
    for p in cleaned_str.split():
        if p.strip():
            files.append(os.path.normpath(p.strip()))
            
    normalized_files = []
    for f in files:
        f_fixed = f.replace('/', '\\')
        if os.path.exists(f_fixed):
            normalized_files.append(f_fixed)
        elif os.path.exists(f):
            normalized_files.append(f)
            
    return normalized_files


class QueueItemFrame(ctk.CTkFrame):
    """대기열에 표시되는 개별 오디오 파일 아이템 행 컴포넌트"""
    def __init__(self, master, file_path, delete_callback, **kwargs):
        super().__init__(master, fg_color="#1E1E2E", corner_radius=6, **kwargs)
        self.file_path = file_path
        self.audio_info = None  # get_audio_info 데이터 저장용
        
        # 파일명 라벨
        filename = os.path.basename(file_path)
        self.name_label = ctk.CTkLabel(
            self, text=filename, anchor="w", font=("Malgun Gothic", 12), text_color="#E0E0E6"
        )
        self.name_label.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=8)
        
        # 원본 정보 표시 (코덱 및 음질 스펙)
        self.src_info_label = ctk.CTkLabel(
            self, text="분석 중...", width=130, font=("Malgun Gothic", 11), text_color="#888888"
        )
        self.src_info_label.pack(side="left", padx=5)
        
        # 목표 정보 표시
        self.tgt_info_label = ctk.CTkLabel(
            self, text="-", width=130, font=("Malgun Gothic", 11), text_color="#888888"
        )
        self.tgt_info_label.pack(side="left", padx=5)
        
        # 상태 표시
        self.status_label = ctk.CTkLabel(
            self, text="대기", width=100, font=("Malgun Gothic", 11, "bold"), text_color="#E5C158"
        )
        self.status_label.pack(side="left", padx=5)
        
        # 개별 제거 버튼
        self.del_btn = ctk.CTkButton(
            self, 
            text="✕", 
            width=28, 
            height=24,
            fg_color="#FF4D4D",
            hover_color="#CC3333",
            font=("Malgun Gothic", 10, "bold"),
            command=lambda: delete_callback(self)
        )
        self.del_btn.pack(side="right", padx=(5, 10))

    def update_status(self, status, text_color=None):
        self.status_label.configure(text=status)
        if text_color:
            self.status_label.configure(text_color=text_color)


class ScrollableQueueFrame(ctk.CTkScrollableFrame):
    """대기열 목록을 관리하는 스크롤 영역"""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="#0F0F1A", label_text="대기열 목록", label_font=("Malgun Gothic", 13, "bold"), label_text_color="#A0A0B0", **kwargs)
        self.items = []
        
    def add_item(self, file_path, delete_callback):
        for item in self.items:
            if item.file_path == file_path:
                return None
                
        item_frame = QueueItemFrame(self, file_path, delete_callback)
        item_frame.pack(fill="x", pady=4, padx=5)
        self.items.append(item_frame)
        return item_frame

    def remove_item(self, item_frame):
        if item_frame in self.items:
            self.items.remove(item_frame)
            item_frame.destroy()
            
    def clear(self):
        for item in self.items:
            item.destroy()
        self.items.clear()


BaseClass = ctk.CTk
if HAS_DND:
    class DnDApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self):
            super().__init__()
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_active = True
            except Exception as e:
                print(f"TkinterDnD2 연동 실패: {e}")
                self.dnd_active = False
    BaseClass = DnDApp


class AudioConverterApp(BaseClass):
    def __init__(self):
        super().__init__()
        
        # 윈도우 기본 설정
        self.title("Audio Bitrate Converter v1.1.0")
        self.geometry("780x740")
        self.minsize(740, 680)
        
        # 윈도우 타이틀바 아이콘 지정
        try:
            if os.path.exists("audio_icon.ico"):
                self.iconbitmap("audio_icon.ico")
        except Exception:
            pass

        
        # 데이터 관리 변수
        self.target_format = ctk.StringVar(value="MP3")
        self.target_bitrate = ctk.StringVar(value="192")
        self.target_bit_depth = ctk.StringVar(value="16")
        self.target_sample_rate = ctk.StringVar(value="44100")
        
        self.save_mode = ctk.StringVar(value="same")
        self.custom_output_path = ctk.StringVar(value="")
        self.name_option = ctk.StringVar(value="suffix")
        self.name_value = ctk.StringVar(value="_192k")
        
        self.is_processing = False
        self.work_queue = queue.Queue()
        self.processed_count = 0
        self.total_count = 0
        
        # GUI 레이아웃 초기화
        self._create_widgets()
        
        # 드래그 앤 드롭 등록
        if HAS_DND and getattr(self, 'dnd_active', False):
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_dnd_drop)
            print("드래그 앤 드롭 기능이 활성화되었습니다.")
        else:
            self.dnd_panel.configure(label_text="[ 드래그 앤 드롭 기능 비활성 - 아래 버튼을 사용해 주세요 ]")

    def _create_widgets(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # 1. 상단 드래그 앤 드롭 & 파일 추가 영역
        self.dnd_panel = ctk.CTkFrame(self, fg_color="#1E1E2E", height=100, corner_radius=8)
        self.dnd_panel.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        
        dnd_label = ctk.CTkLabel(
            self.dnd_panel, 
            text="파일 또는 폴더를 여기에 끌어다 놓으세요 (DSD, WAV, FLAC, APE, MP3, M4A, OGG 지원)", 
            font=("Malgun Gothic", 12, "bold"), 
            text_color="#88889C"
        )
        dnd_label.pack(pady=(15, 5))
        
        btn_frame = ctk.CTkFrame(self.dnd_panel, fg_color="transparent")
        btn_frame.pack(pady=(0, 15))
        
        self.btn_add_files = ctk.CTkButton(
            btn_frame, text="파일 추가...", command=self._browse_files, width=120, height=30, fg_color="#3A86FF", hover_color="#2563EB"
        )
        self.btn_add_files.pack(side="left", padx=10)
        
        self.btn_add_folder = ctk.CTkButton(
            btn_frame, text="폴더 추가...", command=self._browse_folder, width=120, height=30, fg_color="#3A86FF", hover_color="#2563EB"
        )
        self.btn_add_folder.pack(side="left", padx=10)

        # 2. 설정 영역 패널
        self.settings_panel = ctk.CTkFrame(self, fg_color="#1E1E2E", corner_radius=8)
        self.settings_panel.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        self.settings_panel.grid_columnconfigure(1, weight=1)
        
        # 2.1 출력 포맷 선택
        lbl_format = ctk.CTkLabel(self.settings_panel, text="출력 포맷:", font=("Malgun Gothic", 12, "bold"))
        lbl_format.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        self.combo_format = ctk.CTkOptionMenu(
            self.settings_panel,
            values=["MP3", "FLAC", "WAV", "M4A", "OGG"],
            variable=self.target_format,
            width=100,
            command=self._on_target_format_changed
        )
        self.combo_format.grid(row=0, column=1, padx=15, pady=10, sticky="w")
        
        # 2.2 품질 세부 설정 프레임 (동적 UI 레이아웃 구현)
        self.quality_frame = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        self.quality_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=2, sticky="ew")
        self.quality_frame.grid_columnconfigure(1, weight=1)
        
        # 동적 서브 UI 생성 메소드 실행
        self._build_quality_sub_ui()
        
        # 2.3 저장 위치 설정
        lbl_save_loc = ctk.CTkLabel(self.settings_panel, text="저장 위치 설정:", font=("Malgun Gothic", 12, "bold"))
        lbl_save_loc.grid(row=2, column=0, padx=15, pady=5, sticky="nw")
        
        save_loc_frame = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        save_loc_frame.grid(row=2, column=1, padx=15, pady=5, sticky="ew")
        
        self.rdo_save_same = ctk.CTkRadioButton(
            save_loc_frame, text="원본 파일과 동일한 폴더에 저장", variable=self.save_mode, value="same", command=self._toggle_save_ui
        )
        self.rdo_save_same.pack(anchor="w", pady=2)
        
        custom_path_frame = ctk.CTkFrame(save_loc_frame, fg_color="transparent")
        custom_path_frame.pack(fill="x", anchor="w", pady=2)
        
        self.rdo_save_custom = ctk.CTkRadioButton(
            custom_path_frame, text="특정 지정 폴더에 저장", variable=self.save_mode, value="custom", command=self._toggle_save_ui
        )
        self.rdo_save_custom.pack(side="left", padx=(0, 10))
        
        self.entry_custom_path = ctk.CTkEntry(
            custom_path_frame, textvariable=self.custom_output_path, state="disabled", width=250
        )
        self.entry_custom_path.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_browse_out = ctk.CTkButton(
            custom_path_frame, text="변경", state="disabled", command=self._browse_output_dir, width=60, fg_color="#4F5D75", hover_color="#3D4A5E"
        )
        self.btn_browse_out.pack(side="right")
        
        # 2.4 파일명 처리 옵션
        lbl_name_opt = ctk.CTkLabel(self.settings_panel, text="파일명 처리 옵션:", font=("Malgun Gothic", 12, "bold"))
        lbl_name_opt.grid(row=3, column=0, padx=15, pady=10, sticky="nw")
        
        name_opt_frame = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        name_opt_frame.grid(row=3, column=1, padx=15, pady=10, sticky="ew")
        
        self.rdo_name_overwrite = ctk.CTkRadioButton(
            name_opt_frame, text="원본 파일 덮어쓰기 (기본 파일 대체)", variable=self.name_option, value="overwrite", command=self._toggle_name_ui
        )
        self.rdo_name_overwrite.pack(anchor="w", pady=2)
        
        suffix_frame = ctk.CTkFrame(name_opt_frame, fg_color="transparent")
        suffix_frame.pack(fill="x", anchor="w", pady=2)
        
        self.rdo_name_suffix = ctk.CTkRadioButton(
            suffix_frame, text="접미사 추가 -> 형식: 파일명 + [ _192k ] + 확장자", variable=self.name_option, value="suffix", command=self._toggle_name_ui
        )
        self.rdo_name_suffix.pack(side="left", padx=(0, 10))
        
        prefix_frame = ctk.CTkFrame(name_opt_frame, fg_color="transparent")
        prefix_frame.pack(fill="x", anchor="w", pady=2)
        
        self.rdo_name_prefix = ctk.CTkRadioButton(
            prefix_frame, text="접두사 추가 -> 형식: [ [192k]_ ] + 파일명 + 확장자", variable=self.name_option, value="prefix", command=self._toggle_name_ui
        )
        self.rdo_name_prefix.pack(side="left", padx=(0, 10))
        
        self.entry_name_value = ctk.CTkEntry(
            name_opt_frame, textvariable=self.name_value, width=120
        )
        self.entry_name_value.pack(anchor="w", padx=(25, 0), pady=4)

        # 3. 대기열 테이블 타이틀 헤더 프레임
        self.table_header = ctk.CTkFrame(self, fg_color="#1E1E2E", height=30, corner_radius=4)
        self.table_header.grid(row=2, column=0, padx=15, pady=(10, 0), sticky="ew")
        
        lbl_h_name = ctk.CTkLabel(self.table_header, text="파일명", anchor="w", font=("Malgun Gothic", 11, "bold"), text_color="#A0A0B0")
        lbl_h_name.pack(side="left", fill="x", expand=True, padx=(15, 5), pady=4)
        
        lbl_h_src = ctk.CTkLabel(self.table_header, text="원본 스펙", width=130, font=("Malgun Gothic", 11, "bold"), text_color="#A0A0B0")
        lbl_h_src.pack(side="left", padx=5, pady=4)
        
        lbl_h_tgt = ctk.CTkLabel(self.table_header, text="목표 스펙", width=130, font=("Malgun Gothic", 11, "bold"), text_color="#A0A0B0")
        lbl_h_tgt.pack(side="left", padx=5, pady=4)
        
        lbl_h_status = ctk.CTkLabel(self.table_header, text="상태", width=100, font=("Malgun Gothic", 11, "bold"), text_color="#A0A0B0")
        lbl_h_status.pack(side="left", padx=5, pady=4)
        
        lbl_h_dummy = ctk.CTkLabel(self.table_header, text="", width=38)
        lbl_h_dummy.pack(side="right", padx=(5, 10), pady=4)

        # 4. 스크롤 대기열 영역
        self.queue_frame = ScrollableQueueFrame(self)
        self.queue_frame.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="nsew")

        # 5. 진행바 및 제어 버튼
        self.control_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.control_panel.grid(row=4, column=0, padx=15, pady=15, sticky="ew")
        self.control_panel.grid_columnconfigure(0, weight=1)
        
        self.progress_bar = ctk.CTkProgressBar(self.control_panel, height=12, fg_color="#2D2D3D", progress_color="#3A86FF")
        self.progress_bar.grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0.0)
        
        self.lbl_progress = ctk.CTkLabel(self.control_panel, text="대기 중 (0/0)", font=("Malgun Gothic", 12))
        self.lbl_progress.grid(row=1, column=0, sticky="w")
        
        self.btn_clear = ctk.CTkButton(
            self.control_panel, text="대기열 비우기", command=self._clear_queue, width=120, height=35, fg_color="#4F5D75", hover_color="#3D4A5E"
        )
        self.btn_clear.grid(row=1, column=1, padx=5, sticky="e")
        
        self.btn_start = ctk.CTkButton(
            self.control_panel, text="변환 시작", command=self._start_conversion, width=120, height=35, fg_color="#06D6A0", hover_color="#05B98A", text_color="#1E1E2E", font=("Malgun Gothic", 12, "bold")
        )
        self.btn_start.grid(row=1, column=2, padx=5, sticky="e")

    def _build_quality_sub_ui(self):
        """출력 포맷에 따라 손실/무손실 품질 조절 영역을 생성"""
        # 기존 위젯들 정리
        for w in self.quality_frame.winfo_children():
            w.destroy()

        fmt = self.target_format.get()
        if fmt in ["MP3", "M4A", "OGG"]:
            # 손실 압축 비트레이트 컴포넌트
            lbl_bitrate = ctk.CTkLabel(self.quality_frame, text="비트전송률(Bitrate):", font=("Malgun Gothic", 12))
            lbl_bitrate.grid(row=0, column=0, padx=(0, 15), pady=5, sticky="w")
            
            self.combo_bitrate = ctk.CTkOptionMenu(
                self.quality_frame,
                values=["320", "256", "192", "128"],
                variable=self.target_bitrate,
                width=100,
                command=self._on_quality_setting_changed
            )
            self.combo_bitrate.grid(row=0, column=1, pady=5, sticky="w")
        else:
            # 무손실 비트뎁스/샘플레이트 컴포넌트
            lbl_depth = ctk.CTkLabel(self.quality_frame, text="비트뎁스(Bit Depth):", font=("Malgun Gothic", 12))
            lbl_depth.grid(row=0, column=0, padx=(0, 15), pady=5, sticky="w")
            
            self.combo_depth = ctk.CTkOptionMenu(
                self.quality_frame,
                values=["24", "16"],
                variable=self.target_bit_depth,
                width=100,
                command=self._on_quality_setting_changed
            )
            self.combo_depth.grid(row=0, column=1, pady=5, sticky="w")
            
            lbl_sample = ctk.CTkLabel(self.quality_frame, text="샘플레이트(Sample Rate):", font=("Malgun Gothic", 12))
            lbl_sample.grid(row=0, column=2, padx=15, pady=5, sticky="w")
            
            self.combo_sample = ctk.CTkOptionMenu(
                self.quality_frame,
                values=["192000", "96000", "48000", "44100"],
                variable=self.target_sample_rate,
                width=110,
                command=self._on_quality_setting_changed
            )
            self.combo_sample.grid(row=0, column=3, pady=5, sticky="w")

    # GUI 제어 핸들러
    def _toggle_save_ui(self):
        mode = self.save_mode.get()
        if mode == "custom":
            self.entry_custom_path.configure(state="normal")
            self.btn_browse_out.configure(state="normal")
        else:
            self.entry_custom_path.configure(state="disabled")
            self.btn_browse_out.configure(state="disabled")

    def _toggle_name_ui(self):
        opt = self.name_option.get()
        if opt == "overwrite":
            self.entry_name_value.configure(state="disabled")
        else:
            self.entry_name_value.configure(state="normal")
            self._update_name_value_default()

    def _update_name_value_default(self):
        opt = self.name_option.get()
        fmt = self.target_format.get()
        
        if fmt in ["MP3", "M4A", "OGG"]:
            val_suffix = f"_{self.target_bitrate.get()}k"
            val_prefix = f"[{self.target_bitrate.get()}k]_"
        else:
            depth = self.target_bit_depth.get()
            sr_k = int(int(self.target_sample_rate.get()) / 1000)
            val_suffix = f"_{depth}bit_{sr_k}k"
            val_prefix = f"[{depth}bit_{sr_k}k]_"

        if opt == "suffix":
            self.name_value.set(val_suffix)
        elif opt == "prefix":
            self.name_value.set(val_prefix)

    def _on_target_format_changed(self, val):
        # 동적 UI 리컴파일
        self._build_quality_sub_ui()
        # 네이밍 디폴트 갱신
        self._update_name_value_default()
        # 대기열 리스트 동적 업데이트
        self._update_queue_tgt_display()

    def _on_quality_setting_changed(self, val):
        self._update_name_value_default()
        self._update_queue_tgt_display()

    def _get_current_target_setting(self):
        """현재 UI 상태를 기준으로 한 타겟 포맷 설정을 반환"""
        fmt = self.target_format.get()
        if fmt in ["MP3", "M4A", "OGG"]:
            return int(self.target_bitrate.get())
        else:
            return (int(self.target_bit_depth.get()), int(self.target_sample_rate.get()))

    def _get_target_spec_label(self):
        """현재 타겟 스펙 명칭 반환 (예: FLAC 24bit/96k, MP3 192k)"""
        fmt = self.target_format.get()
        if fmt in ["MP3", "M4A", "OGG"]:
            return f"{fmt} {self.target_bitrate.get()}k"
        else:
            sr_k = int(int(self.target_sample_rate.get()) / 1000)
            return f"{fmt} {self.target_bit_depth.get()}bit/{sr_k}k"

    def _update_queue_tgt_display(self):
        tgt_label = self._get_target_spec_label()
        for item in self.queue_frame.items:
            item.tgt_info_label.configure(text=tgt_label)
            self._update_item_status_decision(item)

    def _update_item_status_decision(self, item):
        """원본 오디오 정보와 타겟 품질을 비교하여 인코딩 여부를 판별하고 대기 상태 갱신"""
        if not item.audio_info:
            return  # 아직 분석이 끝나지 않았음

        fmt = self.target_format.get()
        setting = self._get_current_target_setting()
        
        need_encode = should_encode(item.audio_info, fmt, setting)
        
        if need_encode:
            item.update_status("대기", "#E5C158")
        else:
            # 원본보다 높아지거나 동일하여 인코딩 생략 시 '복사(유지)'로 설정
            item.update_status("복사(유지)", "#4AC3FF")

    # 파일 추가 핸들러
    def _browse_files(self):
        file_paths = filedialog.askopenfilenames(
            title="오디오 파일 선택",
            filetypes=[("Audio Files", "*.mp3 *.m4a *.ogg *.flac *.wav *.ape *.dsf *.dff")]
        )
        if file_paths:
            self._add_files_to_queue(file_paths)

    def _browse_folder(self):
        dir_path = filedialog.askdirectory(title="오디오 폴더 선택")
        if dir_path:
            self._add_files_to_queue([dir_path])

    def _browse_output_dir(self):
        dir_path = filedialog.askdirectory(title="저장 폴더 선택")
        if dir_path:
            self.custom_output_path.set(dir_path)

    def _on_dnd_drop(self, event):
        paths = parse_dropped_files(event.data)
        if paths:
            self._add_files_to_queue(paths)

    def _add_files_to_queue(self, paths):
        scanned_files = []
        for path in paths:
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for f in files:
                        if f.lower().endswith(SUPPORTED_EXTENSIONS):
                            scanned_files.append(os.path.join(root, f))
            elif os.path.isfile(path) and path.lower().endswith(SUPPORTED_EXTENSIONS):
                scanned_files.append(path)
                
        new_items = []
        for f in scanned_files:
            item = self.queue_frame.add_item(f, self._delete_queue_item)
            if item:
                new_items.append(item)
                
        self._update_progress_display()
        
        # 백그라운드에서 오디오 규격 분석 실행
        if new_items:
            threading.Thread(target=self._analyze_audio_info_thread, args=(new_items,), daemon=True).start()

    def _delete_queue_item(self, item_frame):
        if self.is_processing:
            return
        self.queue_frame.remove_item(item_frame)
        self._update_progress_display()

    def _clear_queue(self):
        if self.is_processing:
            return
        self.queue_frame.clear()
        self._update_progress_display()
        self.progress_bar.set(0.0)

    def _update_progress_display(self):
        count = len(self.queue_frame.items)
        if self.is_processing:
            self.lbl_progress.configure(text=f"처리 중 ({self.processed_count}/{self.total_count})")
            prog_val = self.processed_count / max(1, self.total_count)
            self.progress_bar.set(prog_val)
        else:
            self.lbl_progress.configure(text=f"대기 중 ({count}개 파일)")
            self.progress_bar.set(0.0)

    # 백그라운드 원본 분석 스레드
    def _analyze_audio_info_thread(self, items):
        for item in items:
            try:
                info = get_audio_info(item.file_path)
                if info:
                    item.audio_info = info
                    # 스펙 라벨 구성
                    src_label = info['format_label']
                    if 'DSD' in src_label:
                        spec_text = src_label
                    elif is_lossless(info['codec_name']):
                        sr_k = int(info['sample_rate'] / 1000)
                        spec_text = f"{src_label} {info['bit_depth']}bit/{sr_k}k"
                    else:
                        br_k = int(info['bit_rate'] / 1000)
                        spec_text = f"{src_label} {br_k}k"
                    
                    item.src_info_label.configure(text=spec_text)
                else:
                    item.src_info_label.configure(text="분석 실패")
            except Exception as e:
                item.src_info_label.configure(text="에러")
                
            # 목표 설정 라벨 갱신 및 상태 연산
            tgt_label = self._get_target_spec_label()
            item.tgt_info_label.configure(text=tgt_label)
            self._update_item_status_decision(item)

    # 변환 실행 핸들러
    def _start_conversion(self):
        if self.is_processing:
            return
            
        items_to_process = self.queue_frame.items
        if not items_to_process:
            messagebox.showwarning("경고", "대기열에 처리할 파일이 없습니다.")
            return

        save_m = self.save_mode.get()
        name_o = self.name_option.get()
        out_dir = self.custom_output_path.get() if save_m == "custom" else ""
        name_val = self.name_value.get() if name_o != "overwrite" else ""
        
        if save_m == "custom" and not out_dir:
            messagebox.showwarning("경고", "저장 폴더 경로를 지정해 주세요.")
            return

        # 덮어쓰기 경고
        if name_o == "overwrite":
            if save_m == "same":
                ans = messagebox.askyesno("경고", "원본 파일과 같은 위치에 '덮어쓰기'를 설정하셨습니다.\n원본 파일이 영구 교체됩니다. 계속하시겠습니까?")
                if not ans:
                    return
            else:
                ans = messagebox.askyesno("확인", "지정 폴더 내에 동일한 파일이 있을 경우 원본 파일이 대체됩니다. 계속하시겠습니까?")
                if not ans:
                    return

        self.is_processing = True
        self.btn_start.configure(state="disabled", fg_color="#5A5A5A", text="처리 중...")
        self.btn_clear.configure(state="disabled")
        self.btn_add_files.configure(state="disabled")
        self.btn_add_folder.configure(state="disabled")
        
        self.processed_count = 0
        self.total_count = len(items_to_process)
        self._update_progress_display()

        self.work_queue = queue.Queue()
        for item in items_to_process:
            self.work_queue.put(item)
            
        # 변환 매개변수 추출
        tgt_fmt = self.target_format.get()
        tgt_setting = self._get_current_target_setting()

        threading.Thread(
            target=self._process_queue_thread, 
            args=(tgt_fmt, tgt_setting, out_dir, name_o, name_val), 
            daemon=True
        ).start()

    def _process_queue_thread(self, target_format, target_setting, output_dir, name_option, value):
        while not self.work_queue.empty():
            item = self.work_queue.get()
            
            curr_status = item.status_label.cget("text")
            if curr_status == "복사(유지)":
                item.update_status("복사 중...", "#3A86FF")
            else:
                item.update_status("변환 중...", "#F77F00")
            
            try:
                status, msg = process_audio(
                    item.file_path,
                    target_format,
                    target_setting,
                    output_dir,
                    name_option,
                    value
                )
                
                if status == 'SUCCESS':
                    item.update_status("완료", "#06D6A0")
                elif status == 'COPY':
                    item.update_status("복사완료", "#06D6A0")
                elif status == 'SKIP':
                    item.update_status("건너뜀", "#888888")
                else:
                    item.update_status("실패", "#FF007F")
                    print(f"변환 실패 ({item.file_path}): {msg}", file=sys.stderr)
            except Exception as e:
                item.update_status("에러", "#FF007F")
                print(f"Exception ({item.file_path}): {e}", file=sys.stderr)

            self.processed_count += 1
            self.after(0, self._update_progress_display)
            self.work_queue.task_done()
            
        self.after(0, self._on_conversion_finished)

    def _on_conversion_finished(self):
        self.is_processing = False
        self.btn_start.configure(state="normal", fg_color="#06D6A0", text="변환 시작")
        self.btn_clear.configure(state="normal")
        self.btn_add_files.configure(state="normal")
        self.btn_add_folder.configure(state="normal")
        
        self._update_progress_display()
        messagebox.showinfo("완료", "모든 오디오 변환/복사 작업이 완료되었습니다!")


if __name__ == "__main__":
    app = AudioConverterApp()
    app.mainloop()
