import type { Metadata } from 'next'
import { Inter, Amiri } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const amiri = Amiri({
  subsets: ['arabic'],
  weight: ['400', '700'],
  variable: '--font-amiri',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'القانون المدني المصري | Egyptian Civil Code Q&A',
  description:
    'Ask questions about the Egyptian Civil Code (1149 articles, Arabic & English). Answers are grounded in article text with citations. General information only — not legal advice.',
  keywords: ['Egyptian Civil Code', 'القانون المدني المصري', 'RAG', 'Legal AI', 'Arabic AI'],
  openGraph: {
    title: 'القانون المدني المصري | Egyptian Civil Code Q&A',
    description: 'AI-powered Q&A for the Egyptian Civil Code with article citations.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ar" dir="rtl" className={`${inter.variable} ${amiri.variable}`}>
      <body>{children}</body>
    </html>
  )
}
