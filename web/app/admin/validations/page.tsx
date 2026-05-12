'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Disagreement {
  id: number;
  raw_item_id: number;
  title: string | null;
  url: string | null;
  llm_said: 'YES' | 'NO';
  keyword_said: 'YES' | 'NO';
  llm_response: string;
  decision_method: string;
  final_result: string;
  created_at: string;
}

interface ReportSummary {
  total_compared: number;
  agreements: number;
  disagreements: number;
  agreement_rate: number;
  llm_more_permissive: number;
  llm_more_strict: number;
  evaluation_mode: boolean;
}

interface LLMReport {
  summary: ReportSummary;
  llm_approved_keyword_rejected: Disagreement[];
  llm_rejected_keyword_approved: Disagreement[];
}

export default function AdminValidationsPage() {
  const [data, setData] = useState<LLMReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [since, setSince] = useState<string>('7d');

  useEffect(() => {
    loadReport();
  }, [since]);

  const loadReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`/api/admin/validations/llm-report?since=${since}`);
      if (!response.ok) {
        throw new Error(`Failed to load report: ${response.statusText}`);
      }
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const truncate = (str: string | null, max: number) => {
    if (!str) return '';
    return str.length > max ? str.slice(0, max) + '...' : str;
  };

  const parseLLMResponse = (response: string): { reason?: string; confidence?: string } => {
    try {
      const parsed = JSON.parse(response);
      return { reason: parsed.reason, confidence: parsed.confidence };
    } catch {
      // Try to extract reason from text format
      const reasonMatch = response.match(/REASON:\s*(.+?)(?:\n|$)/i);
      const confMatch = response.match(/CONFIDENCE:\s*(.+?)(?:\n|$)/i);
      return {
        reason: reasonMatch?.[1] || response.slice(0, 150),
        confidence: confMatch?.[1],
      };
    }
  };

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">LLM Validation Report</h1>
              <p className="text-sm text-gray-500 mt-1">
                Comparing LLM relevance decisions with keyword-based decisions
              </p>
            </div>
            <div className="flex gap-3">
              <Link
                href="/admin/sources"
                className="text-sm text-blue-600 hover:underline"
              >
                Sources
              </Link>
              <Link
                href="/"
                className="text-sm text-blue-600 hover:underline"
              >
                Back to Feed
              </Link>
            </div>
          </div>
        </div>

        {/* Time Filter */}
        <div className="flex gap-2 mb-6">
          {['24h', '7d', '30d'].map((period) => (
            <button
              key={period}
              onClick={() => setSince(period)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                since === period
                  ? 'bg-gray-900 text-white'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              {period === '24h' ? 'Last 24h' : period === '7d' ? 'Last 7 days' : 'Last 30 days'}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600">Loading report...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">
              <strong>Error:</strong> {error}
            </p>
            <button
              onClick={loadReport}
              className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Summary Cards */}
        {data && !loading && (
          <>
            {/* Mode Banner */}
            {data.summary.evaluation_mode && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-6">
                <p className="text-sm text-amber-800">
                  <strong>Evaluation Mode Active:</strong> Keyword decisions are authoritative.
                  LLM runs alongside for comparison only.
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <p className="text-2xl font-bold text-gray-900">{data.summary.total_compared}</p>
                <p className="text-sm text-gray-500">Total Compared</p>
              </div>
              <div className="bg-white rounded-lg border border-green-200 p-4">
                <p className="text-2xl font-bold text-green-700">
                  {data.summary.agreement_rate}%
                </p>
                <p className="text-sm text-gray-500">
                  Agreement ({data.summary.agreements})
                </p>
              </div>
              <div className="bg-white rounded-lg border border-blue-200 p-4">
                <p className="text-2xl font-bold text-blue-700">
                  {data.summary.llm_more_permissive}
                </p>
                <p className="text-sm text-gray-500">LLM More Permissive</p>
              </div>
              <div className="bg-white rounded-lg border border-orange-200 p-4">
                <p className="text-2xl font-bold text-orange-700">
                  {data.summary.llm_more_strict}
                </p>
                <p className="text-sm text-gray-500">LLM More Strict</p>
              </div>
            </div>

            {/* Disagreements: LLM approved, keyword rejected */}
            {data.llm_approved_keyword_rejected.length > 0 && (
              <div className="mb-8">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">
                  LLM Approved, Keyword Rejected
                  <span className="ml-2 text-sm font-normal text-blue-600">
                    ({data.llm_approved_keyword_rejected.length})
                  </span>
                </h2>
                <p className="text-sm text-gray-500 mb-3">
                  Articles the LLM thinks are relevant but keywords missed. These may be false negatives in keyword matching.
                </p>
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Article</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">LLM Reason</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Final</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">When</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {data.llm_approved_keyword_rejected.map((item) => {
                          const parsed = parseLLMResponse(item.llm_response);
                          return (
                            <tr key={item.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3 max-w-xs">
                                <p className="text-sm font-medium text-gray-900">
                                  {truncate(item.title, 80)}
                                </p>
                                {item.url && (
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-blue-500 hover:underline truncate block max-w-xs"
                                  >
                                    {truncate(item.url, 50)}
                                  </a>
                                )}
                              </td>
                              <td className="px-4 py-3 max-w-sm">
                                <p className="text-sm text-gray-600">
                                  {truncate(parsed.reason || item.llm_response, 120)}
                                </p>
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                                  item.final_result === 'approved'
                                    ? 'bg-green-100 text-green-800'
                                    : 'bg-red-100 text-red-800'
                                }`}>
                                  {item.final_result}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                                {formatTime(item.created_at)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* Disagreements: LLM rejected, keyword approved */}
            {data.llm_rejected_keyword_approved.length > 0 && (
              <div className="mb-8">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">
                  LLM Rejected, Keyword Approved
                  <span className="ml-2 text-sm font-normal text-orange-600">
                    ({data.llm_rejected_keyword_approved.length})
                  </span>
                </h2>
                <p className="text-sm text-gray-500 mb-3">
                  Articles the LLM thinks are irrelevant but keywords accepted. These may be false positives in keyword matching.
                </p>
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Article</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">LLM Reason</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Final</th>
                          <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">When</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {data.llm_rejected_keyword_approved.map((item) => {
                          const parsed = parseLLMResponse(item.llm_response);
                          return (
                            <tr key={item.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3 max-w-xs">
                                <p className="text-sm font-medium text-gray-900">
                                  {truncate(item.title, 80)}
                                </p>
                                {item.url && (
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-blue-500 hover:underline truncate block max-w-xs"
                                  >
                                    {truncate(item.url, 50)}
                                  </a>
                                )}
                              </td>
                              <td className="px-4 py-3 max-w-sm">
                                <p className="text-sm text-gray-600">
                                  {truncate(parsed.reason || item.llm_response, 120)}
                                </p>
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                                  item.final_result === 'approved'
                                    ? 'bg-green-100 text-green-800'
                                    : 'bg-red-100 text-red-800'
                                }`}>
                                  {item.final_result}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                                {formatTime(item.created_at)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* No disagreements */}
            {data.llm_approved_keyword_rejected.length === 0 &&
             data.llm_rejected_keyword_approved.length === 0 && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center mb-8">
                <p className="text-green-800 font-medium">
                  No disagreements found in this period.
                </p>
                <p className="text-sm text-green-600 mt-1">
                  LLM and keyword decisions are in full agreement.
                </p>
              </div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-400">
          <p>Sharks News Aggregator - Admin Panel</p>
        </div>
      </div>
    </main>
  );
}
