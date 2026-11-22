import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** A new page starts at its top (the pages scroll in their own `.lg-back` boxes as well as the window). */
export function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
    document.querySelectorAll<HTMLElement>(".lg-back").forEach((el) => {
      el.scrollTop = 0;
    });
  }, [pathname]);
  return null;
}
