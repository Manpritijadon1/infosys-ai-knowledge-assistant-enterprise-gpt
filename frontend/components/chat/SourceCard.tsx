
"use client";

import React, { useState } from "react";
import {
  FileText,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { SourceCitation } from "@/types";
import { api } from "@/lib/api";

interface SourceCardProps {
  sources: SourceCitation[];
}

export function SourceCard({ sources }: SourceCardProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!sources || sources.length === 0) return null;

  const handleOpenPDF = async (
    event: React.MouseEvent<HTMLButtonElement>,
    source: SourceCitation,
    index: number
  ) => {
    event.stopPropagation();
    setError(null);

    if (source.document_db_id == null) {
      setError("Document ID is unavailable. Please refresh and try again.");
      return;
    }

    // Open synchronously to avoid popup blockers.
    const newWindow = window.open("", "_blank");

    if (!newWindow) {
      setError("Please allow pop-ups to open the PDF document.");
      return;
    }

    try {
      setLoadingIndex(index);

      const pdfBlob = await api.viewDocument(source.document_db_id);

      if (pdfBlob.type && !pdfBlob.type.includes("pdf")) {
        throw new Error("The server did not return a PDF file.");
      }

      const pdfUrl = URL.createObjectURL(pdfBlob);

      newWindow.location.href =
        `${pdfUrl}#page=${source.page_number || 1}`;

    } catch (err) {
      newWindow.close();

      setError(
        err instanceof Error
          ? err.message
          : "Unable to open the PDF document."
      );
    } finally {
      setLoadingIndex(null);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-slate-100">

      {/* Sources Accordion Toggle */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-xs font-bold text-slate-700 hover:text-[#1E60FF] transition-colors mb-2"
      >
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
        )}

        <span>Sources ({sources.length})</span>
      </button>

      {error && (
        <p className="text-xs text-red-600 mb-2">{error}</p>
      )}

      {isOpen && (
        <div className="space-y-2">

          {sources.map((source, index) => {
            const isExpanded = expandedIndex === index;
            const isLoading = loadingIndex === index;

            return (
              <div
                key={`${source.document_db_id}-${source.page_number}-${index}`}
                className="rounded-xl border border-slate-200/90 bg-[#F8FAFC] hover:bg-white hover:border-[#1E60FF]/40 transition-all overflow-hidden"
              >
                <div className="flex items-center justify-between p-2.5">

                  <div className="flex items-center gap-2.5 min-w-0 flex-1">

                    <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0 border border-rose-100">
                      <FileText className="w-4 h-4" />
                    </div>

                    <div className="min-w-0 flex-1">

                      {/* Clicking document title opens PDF */}
                      <button
                        type="button"
                        onClick={(event) =>
                          handleOpenPDF(event, source, index)
                        }
                        disabled={
                          isLoading || source.document_db_id == null
                        }
                        className="text-left w-full text-xs font-bold text-slate-800 hover:text-[#1E60FF] truncate disabled:opacity-50"
                        title="Open original PDF"
                      >
                        {source.document_title}
                      </button>

                      <p className="text-[11px] text-slate-500">
                        Page {source.page_number} • Similarity:{" "}
                        <span className="font-semibold text-emerald-600">
                          {source.similarity.toFixed(4)}
                        </span>

                        {source.department && ` • ${source.department}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">

                    {/* Open Original PDF */}
                    <button
                      type="button"
                      onClick={(event) =>
                        handleOpenPDF(event, source, index)
                      }
                      disabled={
                        isLoading || source.document_db_id == null
                      }
                      title="Open original PDF"
                      className="text-slate-400 hover:text-[#1E60FF] disabled:opacity-40 p-1.5 rounded-md hover:bg-blue-50 transition-colors"
                    >
                      {isLoading ? (
                        <span className="block w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <ExternalLink className="w-4 h-4" />
                      )}
                    </button>

                    {/* Expand / Collapse Excerpt */}
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedIndex(isExpanded ? null : index)
                      }
                      title={isExpanded ? "Collapse excerpt" : "Show excerpt"}
                      className="text-slate-400 hover:text-slate-600 p-1.5 rounded-md hover:bg-slate-100"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>

                  </div>
                </div>

                {isExpanded && (
                  <div className="px-3 pb-3 pt-1 border-t border-slate-100 text-xs text-slate-600 bg-white leading-relaxed">

                    <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                      Matched Document Excerpt:
                    </p>

                    <p className="p-2 rounded bg-slate-50 border border-slate-100 italic">
                      "{source.content_snippet ||
                        "Relevant document context utilized for answering this query."}"
                    </p>

                  </div>
                )}
              </div>
            );
          })}

        </div>
      )}
    </div>
  );
}
