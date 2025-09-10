import { Layout } from "@/components/Layout";
import { AppProvider } from "@/lib/state/AppContext";
import MainArea from "@/components/MainArea";

export default function Home() {
  return (
    <AppProvider>
      <Layout>
        <MainArea />
      </Layout>
    </AppProvider>
  );
}
