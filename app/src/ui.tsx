// 이 앱의 부품. 공통 부품(Icon, Screen, Modal …)은 common.tsx에 있고 여기서 다시 내보낸다.
import type { ReactNode } from "react";

export * from "./common";

/** 꺾쇠(jamak과 한 계열) + 소리 막대 세 개 + 흘러가는 화살표(변환). 색은 팔레트와 관계없이 고정이다. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path className="corner" d="M3 11V3h8M29 21v8h-8" />
      <path className="wave" d="M8 13v6M12 9v14M16 12v8" />
      <path className="ff" d="M20 12l4 4-4 4" />
    </svg>
  );
}

/** 머리글 위 작은 줄: 영문 대문자 이름(자간 있음) + 한글 요약(자간 없음). */
export function eyebrow(tag: string, summary?: ReactNode): ReactNode {
  return <><span className="tracked">{tag}</span>{summary ? <> · {summary}</> : null}</>;
}

/** 여러 값 중 하나를 고르는 버튼 묶음 */
export function Seg<T extends string | number>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={value === o.value} disabled={disabled}
          onClick={() => value !== o.value && onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}
