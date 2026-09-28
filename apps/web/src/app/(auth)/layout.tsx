import styles from "./auth.module.css";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className={styles.page}>
      <div className={`panel panel-pad ${styles.card}`}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden>AI</span>
          <span>Business Office</span>
        </div>
        {children}
      </div>
    </main>
  );
}
