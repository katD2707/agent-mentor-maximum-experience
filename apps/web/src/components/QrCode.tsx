"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

/** QR code rendered client-side (no network). */
export function QrCode({ value, label, size = 200 }: { value: string; label: string; size?: number }) {
  const [src, setSrc] = useState<{ value: string; url: string } | null>(null);

  useEffect(() => {
    let alive = true;
    QRCode.toDataURL(value, { margin: 1, width: size * 2, errorCorrectionLevel: "M" }).then(
      (url) => alive && setSrc({ value, url }),
      () => alive && setSrc(null),
    );
    return () => {
      alive = false;
    };
  }, [value, size]);

  if (!src || src.value !== value) {
    return <div style={{ width: size, height: size }} className="faint" aria-busy="true" />;
  }
  // A locally generated data URL; next/image adds nothing here.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src.url} alt={label} width={size} height={size} />;
}
