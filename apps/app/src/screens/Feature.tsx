import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon } from "../components/Icon";

/** Placeholder for Khóa học / Luyện tập / Hỏi đáp / Tiến độ: only a small back button and the title. */
export function Feature({ id }: { id: "practice" | "ask" }) {
  const { t } = useTranslation();
  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t(`hub.${id}`)}</h1>
      </header>
      <main className="main feature-main">
        <section className="wip oli">
          <h2>{t("wip.title")}</h2>
          <p className="muted">{t("wip.body")}</p>
        </section>
      </main>
    </div>
  );
}
