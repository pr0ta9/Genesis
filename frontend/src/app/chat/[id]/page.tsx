"use client";
import { useEffect } from "react";
import { useRouter, useParams, usePathname } from "next/navigation";
import { Layout } from "@/components/Layout";
import MainArea from "@/components/MainArea";
import { AppProvider, useApp } from "@/lib/state/AppContext";

function ChatByIdInner() {
  const params = useParams<{ id: string }>();
  const { dispatch, currentConversationId } = useApp();
  const pathname = usePathname();

  useEffect(() => {
    const id = params?.id;
    if (id && id !== currentConversationId) {
      dispatch({ type: "set_current_conversation", id });
    }
  }, [params?.id, currentConversationId, dispatch]);

  return (
    <Layout>
      <MainArea />
    </Layout>
  );
}

export default function ChatByIdPage() {
  return (
    <AppProvider>
      <ChatByIdInner />
    </AppProvider>
  );
}


