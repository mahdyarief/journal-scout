import { Card, Chip, LINK_CLASS, PageHeader, Panel } from "../components/ui";

type ToolEntry = {
  name: string;
  purpose: string;
  group: "Search" | "Papers" | "Graph & metrics" | "Export & archive" | "Review (SLR)" | "Keys";
};

const MCP_URL =
  typeof window === "undefined"
    ? "/mcp"
    : `${window.location.origin}/mcp`;

const TOOLS: ToolEntry[] = [
  { name: "search_all", group: "Search", purpose: "Cari semua sumber secara paralel lalu gabungkan duplikat berdasarkan DOI/judul." },
  { name: "search_author", group: "Search", purpose: "Cari semua paper dari satu penulis lintas sumber (Scopus, Crossref, OpenAlex, arXiv), lalu digabung dan dideduplikasi." },
  { name: "search_scopus", group: "Search", purpose: "Cari hanya di Scopus." },
  { name: "search_arxiv", group: "Search", purpose: "Cari hanya di arXiv." },
  { name: "search_openalex", group: "Search", purpose: "Cari hanya di OpenAlex." },
  { name: "search_crossref", group: "Search", purpose: "Cari hanya di Crossref." },
  { name: "search_pubmed", group: "Search", purpose: "Cari hanya di PubMed." },
  { name: "search_garuda", group: "Search", purpose: "Cari hanya di Garuda." },
  { name: "search_consensus", group: "Search", purpose: "Cari hanya di Consensus." },
  { name: "search_exa", group: "Search", purpose: "Cari web melalui Exa (endpoint MCP publik; tidak perlu API key)." },
  { name: "search_corpus", group: "Search", purpose: "Cari teks (judul, abstrak, venue, penulis, kata kunci) pada hasil pencarian yang sudah diarsipkan lokal — tanpa request jaringan." },
  { name: "get_paper", group: "Papers", purpose: "Ambil satu paper berdasarkan DOI / id arXiv / Scopus / OpenAlex, gabungkan metadata, dan lampirkan tautan akses terbuka." },
  { name: "get_paper_abstract", group: "Papers", purpose: "Cari abstrak satu paper (berdasarkan DOI, identifier lain, atau judul) dari semua sumber yang bisa menjawab. Mengembalikan status not_found dan abstrak null bila tidak ada — tidak menebak dari judul." },
  { name: "get_abstracts", group: "Papers", purpose: "Isi abstrak yang kosong pada daftar paper (misalnya hasil search_all). Urutan tetap, abstrak yang sudah ada tidak ditimpa, dan status tiap paper dilaporkan." },
  { name: "get_references", group: "Graph & metrics", purpose: "Kumpulkan daftar referensi satu paper dari semua sumber yang menyediakannya (Scopus/OpenAlex/Crossref/OpenCitations), digabung dan dideduplikasi." },
  { name: "get_citations", group: "Graph & metrics", purpose: "Kumpulkan paper yang mengutip satu paper lintas sumber (Scopus + OpenAlex + OpenCitations)." },
  { name: "get_related_works", group: "Graph & metrics", purpose: "Tampilkan paper terkait menurut OpenAlex (mirip fitur Related Works di Publish or Perish), digabung dan dideduplikasi." },
  { name: "build_citation_network", group: "Graph & metrics", purpose: "Bangun jaringan sitasi di sekitar satu paper: kutipan langsung, bibliographic coupling, dan co-citation. graph_format=graphml menghasilkan berkas untuk Gephi/VOSviewer." },
  { name: "build_research_landscape", group: "Graph & metrics", purpose: "Cari kata kunci lalu kelompokkan korpus hasil menjadi peta riset: klaster TF-IDF, label c-TF-IDF, koordinat 2D, serta statistik topik/penulis/venue per klaster." },
  { name: "compute_metrics", group: "Graph & metrics", purpose: "Hitung metrik ala Publish or Perish (jumlah paper, total sitasi, h-index, i10, g-index, kecepatan sitasi) untuk nama penulis atau query." },
  { name: "get_abstract_details", group: "Keys", purpose: "Detail abstrak Scopus untuk Scopus id." },
  { name: "get_author_profile", group: "Keys", purpose: "Profil penulis dari Scopus." },
  { name: "get_quota_status", group: "Keys", purpose: "Batas laju dan status kuota setiap sumber yang terkonfigurasi, termasuk header Scopus langsung bila tersedia." },
  { name: "scival_author_metrics", group: "Keys", purpose: "Metrik penulis dari SciVal." },
  { name: "scival_institution_metrics", group: "Keys", purpose: "Metrik institusi dari SciVal." },
  { name: "scival_author_lookup", group: "Keys", purpose: "Cari penulis di SciVal berdasarkan nama." },
  { name: "scival_institution_lookup", group: "Keys", purpose: "Cari institusi di SciVal berdasarkan nama." },
  { name: "scival_topic_metrics", group: "Keys", purpose: "Metrik topik dari SciVal." },
  { name: "rotate_consensus_key", group: "Keys", purpose: "Verifikasi kunci Consensus baru ke API; hanya disimpan bila diterima. Kunci lama tetap aman bila verifikasi gagal." },
  { name: "export_results", group: "Export & archive", purpose: "Ekspor daftar paper ke BibTeX, RIS, CSV, EndNote, WoS, gaya sitasi, atau JSON." },
  { name: "identify_paper", group: "Export & archive", purpose: "Kenali paper dari berkas PDF lokal dengan resolusi DOI atau judul." },
  { name: "check_watches", group: "Export & archive", purpose: "Jalankan semua watch pencarian tersimpan dan kembalikan paper yang belum pernah dilaporkan." },
  { name: "slr_import", group: "Review (SLR)", purpose: "Impor catatan ke state review SLR (dedup berdasarkan DOI lalu judul) dari hasil pencarian." },
  { name: "slr_screen", group: "Review (SLR)", purpose: "Catat keputusan screening judul/abstrak untuk satu catatan: include/exclude/unclear disertai kode alasan." },
  { name: "slr_full_text", group: "Review (SLR)", purpose: "Catat keputusan kelayakan full-text untuk satu catatan: include/exclude disertai alasan." },
  { name: "slr_appraise", group: "Review (SLR)", purpose: "Catat penilaian kualitas studi yang termasuk: kelas, butir Y/T, dan risiko." },
  { name: "slr_extract", group: "Review (SLR)", purpose: "Simpan field ekstraksi (tahun, metrik, dll.) untuk studi yang termasuk." },
  { name: "slr_prisma", group: "Review (SLR)", purpose: "Hitung alur PRISMA 2020 dari state review saat ini." },
  { name: "slr_summary", group: "Review (SLR)", purpose: "Snapshot SLR lengkap (PRISMA + keputusan tiap catatan), atau CSV dengan format=csv." },
  { name: "slr_reset", group: "Review (SLR)", purpose: "Hapus seluruh state review SLR." },
];

const GROUPS: ToolEntry["group"][] = [
  "Search",
  "Papers",
  "Graph & metrics",
  "Export & archive",
  "Review (SLR)",
  "Keys",
];

export function DocsPage() {
  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="Using the MCP server"
        description="Hubungkan klien MCP ke journal-scout, lalu panggil tools untuk mencari, menggabungkan, dan mengekspor literatur."
      />

      <Panel className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold">Connect a client</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Endpoint Streamable HTTP tersedia di <code>{MCP_URL}</code>. Untuk
            deploy publik, sertakan bearer token bila <code>JOSC_MCP_TOKEN</code>{" "}
            diaktifkan.
          </p>
        </div>
        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
          {`{
  "mcpServers": {
    "journal-scout": {
      "type": "http",
      "url": "${MCP_URL}"
    }
  }
}`}
        </pre>
        <div className="flex flex-wrap gap-2">
          <a className={LINK_CLASS} href="/healthz" target="_blank" rel="noreferrer">
            Health check
          </a>
        </div>
      </Panel>

      <Card className="space-y-2">
        <h2 className="text-sm font-semibold">Contoh alur</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>
            <code>search_all</code> dengan query boolean uppercase:{" "}
            <code>&quot;insurance AND AI&quot;</code>. Operator lowercase tidak
            diterjemahkan.
          </li>
          <li>
            <code>get_abstracts</code> dengan hasil tersebut untuk melengkapi
            abstrak yang kosong.
          </li>
          <li>
            <code>get_citations</code> atau <code>build_citation_network</code>{" "}
            untuk menelusuri kutipan, lalu <code>export_results</code> untuk
            BibTeX/CSV.
          </li>
        </ol>
        <p className="text-xs text-muted-foreground">
          Selalu cek field <code>errors</code> pada respons: satu sumber yang
          gagal tidak menggagalkan pencarian, tetapi hasilnya jadi tidak lengkap.
        </p>
      </Card>

      <div className="space-y-3">
        {GROUPS.map((group) => (
          <Panel key={group} className="space-y-2">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold">{group}</h2>
              <Chip variant="secondary">
                {TOOLS.filter((t) => t.group === group).length}
              </Chip>
            </div>
            <dl className="divide-y divide-border text-sm">
              {TOOLS.filter((t) => t.group === group).map((tool) => (
                <div key={tool.name} className="grid gap-1 py-2 sm:grid-cols-[minmax(0,14rem)_1fr] sm:gap-4">
                  <dt>
                    <code className="text-xs font-medium">{tool.name}</code>
                  </dt>
                  <dd className="text-muted-foreground">{tool.purpose}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        ))}
      </div>
    </div>
  );
}
