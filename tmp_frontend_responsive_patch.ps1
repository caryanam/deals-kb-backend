$frontend = "C:\Users\Laptop On Rent 248\Downloads\Project - Dealskb\deals-kb-frontend"

function Update-File {
    param(
        [string]$Path,
        [scriptblock]$Transform
    )

    $fullPath = Join-Path $frontend $Path
    $content = Get-Content -LiteralPath $fullPath -Raw
    $updated = & $Transform $content
    if ($updated -ne $content) {
        Set-Content -LiteralPath $fullPath -Value $updated -Encoding UTF8
    }
}

Update-File "src\styles\globals.css" {
    param($content)

    $replacement = @'
.dashboard-shell {
  min-height: 100dvh;
  background: #fbf5ea;
  overflow-x: clip;
}

.dashboard-scroll-page {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: #fbf5ea;
}

.dashboard-main-area {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  align-items: stretch;
  flex: 1;
}

.dashboard-sidebar {
  width: 260px;
  min-width: 260px;
  flex-shrink: 0;
  min-height: 100dvh;
  position: sticky;
  top: 0;
  align-self: start;
  background: linear-gradient(180deg, #3b0038 0%, #4b003f 45%, #260027 100%);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  box-shadow: 4px 0 18px rgba(0, 0, 0, 0.16);
  z-index: 50;
}

.sidebar-logo {
  height: 88px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 24px;
  font-size: 24px;
  font-weight: 800;
  color: #ffffff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.sidebar-menu {
  padding: 24px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.sidebar-item,
.sidebar-link {
  height: 50px;
  padding: 0 20px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 14px;
  color: rgba(255, 255, 255, 0.68) !important;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sidebar-item:hover,
.sidebar-link:hover {
  background: rgba(255, 255, 255, 0.08) !important;
  color: #ffffff !important;
}

.sidebar-item.active,
.sidebar-link.active,
.sidebar-link-active {
  background: linear-gradient(90deg, #8b1686 0%, #94168d 100%) !important;
  color: #ffffff !important;
  box-shadow: inset 4px 0 0 #00d1b2 !important;
}

.dashboard-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.dashboard-topbar,
.dashboard-header,
.topbar-wrapper {
  min-height: 72px !important;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 40;
  background: #fffaf0;
  border-bottom: 1px solid rgba(80, 0, 70, 0.14);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0 32px !important;
}

.dashboard-topbar-left,
.dashboard-topbar-right,
.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.dashboard-topbar-left,
.dashboard-topbar-right {
  min-width: 0;
}

.dashboard-topbar-title,
.dashboard-header h2,
.topbar-title {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: #111111;
}

.user-badge {
  font-weight: 700;
  color: #3b0038;
}

.logout-btn {
  height: 40px;
  padding: 0 18px;
  border-radius: 8px;
  border: 1px solid #ffb3b3;
  background: #fff7f7;
  color: #ff3333;
  font-weight: 700;
  cursor: pointer;
}

.dashboard-content {
  flex: 1;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 28px 32px 48px;
  background: #fbf5ea;
}

.app-container,
.dashboard-page {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}

.responsive-banner,
.responsive-page-header {
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  gap: 1rem !important;
  flex-wrap: wrap !important;
}

.responsive-banner-actions,
.responsive-page-actions {
  display: flex !important;
  align-items: center !important;
  gap: 0.75rem !important;
  flex-wrap: wrap !important;
}

.responsive-stats-grid-4 {
  display: grid !important;
  grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
  gap: 1.25rem !important;
}

.responsive-stats-grid-5 {
  display: grid !important;
  grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
  gap: 1.25rem !important;
}

.responsive-main-split,
.responsive-auction-grid,
.responsive-listing-form,
.responsive-listing-form--relist,
.admin-products-layout {
  display: grid !important;
  gap: 1.5rem !important;
}

.responsive-listing-form {
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr) !important;
}

.responsive-listing-form--relist {
  grid-template-columns: 1.6fr 1fr !important;
}

.responsive-fields-2 {
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  gap: 1rem !important;
}

.responsive-fields-3 {
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: 1rem !important;
}

.responsive-photo-grid {
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  gap: 0.75rem !important;
}

.responsive-filter-row {
  display: flex !important;
  gap: 1rem !important;
  flex-wrap: wrap !important;
}

.responsive-form-sidebar,
.responsive-form-main {
  min-width: 0;
}

.responsive-form-actions {
  display: flex !important;
  align-items: stretch !important;
  gap: 0.85rem !important;
  flex-wrap: wrap !important;
}

.seller-listing-detail-grid {
  display: grid !important;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.95fr) !important;
  gap: 1.5rem !important;
}

.seller-listing-photo-grid {
  display: grid !important;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)) !important;
  gap: 0.9rem !important;
}

.seller-listing-spec-grid {
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  gap: 0.8rem !important;
}

.dashboard-scroll-page footer,
.dashboard-scroll-page .site-footer,
.dashboard-scroll-page .dashboard-footer {
  width: 100% !important;
  margin: 0 !important;
  background: #060b14;
  color: #ffffff;
  position: relative;
  z-index: 100;
}

.mobile-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(31, 26, 29, 0.65);
  z-index: 45;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--transition-normal);
}

.mobile-backdrop.backdrop-open {
  opacity: 1;
  pointer-events: auto;
}

@media (max-width: 1280px) {
  .dashboard-content {
    padding: 24px 24px 40px;
  }

  .dashboard-topbar,
  .dashboard-header,
  .topbar-wrapper {
    padding: 0 24px !important;
  }
}

@media (max-width: 1100px) {
  .responsive-stats-grid-5 {
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  }

  .responsive-listing-form,
  .responsive-listing-form--relist,
  .responsive-auction-grid,
  .seller-listing-detail-grid,
  .admin-products-layout {
    grid-template-columns: minmax(0, 1fr) !important;
  }
}

@media (max-width: 1024px) {
  .dashboard-main-area {
    grid-template-columns: 232px minmax(0, 1fr);
  }

  .dashboard-sidebar {
    width: 232px;
    min-width: 232px;
  }

  .responsive-stats-grid-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }

  .responsive-stats-grid-5 {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }

  .responsive-fields-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }

  .dashboard-topbar,
  .dashboard-header,
  .topbar-wrapper {
    min-height: 72px !important;
    padding: 12px 20px !important;
  }
}

@media (max-width: 768px) {
  .dashboard-shell,
  .dashboard-scroll-page,
  .dashboard-main-area {
    min-height: 100dvh;
  }

  .dashboard-main-area {
    display: block;
  }

  .dashboard-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    width: min(82vw, 300px);
    min-width: min(82vw, 300px);
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    z-index: 60;
  }

  .dashboard-sidebar.open {
    transform: translateX(0);
  }

  .dashboard-right {
    width: 100%;
  }

  .dashboard-topbar,
  .dashboard-header,
  .topbar-wrapper {
    min-height: 72px !important;
    padding: 12px 16px !important;
    align-items: flex-start !important;
    flex-wrap: wrap !important;
  }

  .dashboard-topbar-left,
  .dashboard-topbar-right {
    width: 100%;
    justify-content: space-between;
    gap: 0.75rem !important;
    flex-wrap: wrap;
  }

  .dashboard-topbar-title {
    font-size: 1.05rem !important;
  }

  .dashboard-content {
    padding: 20px 16px 32px;
  }

  .responsive-banner,
  .responsive-page-header {
    align-items: flex-start !important;
  }

  .responsive-banner-actions,
  .responsive-page-actions {
    width: 100%;
    justify-content: flex-start !important;
  }

  .responsive-fields-2,
  .responsive-fields-3,
  .responsive-photo-grid,
  .seller-listing-spec-grid {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  .seller-listing-photo-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }

  .responsive-stats-grid-4,
  .responsive-stats-grid-5 {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  .mobile-toggle {
    display: inline-flex !important;
  }
}

@media (max-width: 560px) {
  .dashboard-topbar-right > * {
    max-width: 100%;
  }

  .seller-listing-photo-grid {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  .responsive-form-actions > * {
    flex: 1 1 100% !important;
    width: 100%;
  }
}
'@

    return [regex]::Replace(
        $content,
        '(?s)\.dashboard-shell\s*\{.*?\.mobile-backdrop\.backdrop-open\s*\{\s*opacity:\s*1;\s*pointer-events:\s*auto;\s*\}',
        $replacement
    )
}

Update-File "src\components\layout\Topbar.jsx" {
    param($content)

    $content = $content.Replace("<header style={{", "<header className=""dashboard-topbar"" style={{")
    $content = $content -replace '(/\* Left side: Hamburger and title \*/\s*<div) style=\{\{ display: ''flex'', alignItems: ''center'', gap: ''1rem'' \}\}>', '$1 className="dashboard-topbar-left" style={{ display: ''flex'', alignItems: ''center'', gap: ''1rem'' }}>'
    $content = $content -replace '(<h2) style=\{\{ fontSize: ''1\.25rem'', fontWeight: 700, letterSpacing: ''-0\.02em'', color: ''#1F1A1D'' \}\}>', '$1 className="dashboard-topbar-title" style={{ fontSize: ''1.25rem'', fontWeight: 700, letterSpacing: ''-0.02em'', color: ''#1F1A1D'' }}>'
    $content = $content -replace '(/\* Right side: Chats, Notifications, Profile, Logout \*/\s*<div) style=\{\{ display: ''flex'', alignItems: ''center'', gap: ''1\.5rem'' \}\}>', '$1 className="dashboard-topbar-right" style={{ display: ''flex'', alignItems: ''center'', gap: ''1.5rem'' }}>'
    return $content
}

Update-File "src\pages\buyer\BuyerDashboard.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',","<div className=""responsive-banner"" style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',")
    $content = $content.Replace("<div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>","<div className=""responsive-banner-actions"" style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>","<div className=""responsive-stats-grid-4"" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>")
    $content = $content.Replace("className=""grid-cols-2""","className=""grid-cols-2 responsive-main-split""")
    return $content
}

Update-File "src\pages\seller\SellerDashboard.jsx" {
    param($content)
    $content = $content.Replace("import { getProducts } from '../../api/productApi';`r`nimport { getMyPlans } from '../../api/paymentApi';","import { getProducts } from '../../api/productApi';`r`nimport { getMyPlans } from '../../api/paymentApi';`r`nimport { toast } from 'react-toastify';")
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',","<div className=""responsive-banner"" style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',")
    $content = $content.Replace("<div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>","<div className=""responsive-banner-actions"" style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>","<div className=""responsive-stats-grid-5"" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>")
    $content = $content.Replace("className=""grid-cols-2""","className=""grid-cols-2 responsive-main-split""")
    return $content
}

Update-File "src\pages\admin\AdminDashboard.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',","<div className=""responsive-banner"" style={{`r`n        background: 'linear-gradient(to right, #1F1A1D, #2d0a32)',")
    $content = $content.Replace("<div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>","<div className=""responsive-banner-actions"" style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>")
    return $content
}

Update-File "src\pages\buyer\MarketplacePage.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>","<div className=""responsive-page-header"" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>","<div className=""responsive-page-actions"" style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>","<div className=""responsive-filter-row"" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>")
    return $content
}

Update-File "src\pages\buyer\LiveAuctionPage.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>","<div className=""responsive-page-header"" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>","<div className=""responsive-page-actions"" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>")
    $content = $content.Replace("className=""grid-cols-2""","className=""grid-cols-2 responsive-auction-grid""")
    return $content
}

Update-File "src\pages\seller\SellerAuctionPage.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>","<div className=""responsive-page-header"" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>","<div className=""responsive-page-actions"" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>")
    $content = $content.Replace("className=""grid-cols-2""","className=""grid-cols-2 responsive-auction-grid""")
    return $content
}

Update-File "src\pages\admin\AdminProductsPage.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>","<div className=""dashboard-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"" }}>")
    $content = $content.Replace("<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>","<div className=""responsive-page-header"" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: selectedLiveId ? '1.4fr 1fr' : '1fr', gap: '1.5rem', alignItems: 'start' }}>","<div className=""admin-products-layout"" style={{ display: 'grid', gridTemplateColumns: selectedLiveId ? '1.4fr 1fr' : '1fr', gap: '1.5rem', alignItems: 'start' }}>")
    return $content
}

Update-File "src\pages\seller\CreateListingPage.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"", maxWidth: '1120px', margin: '0 auto' }}>","<div className=""dashboard-page listing-form-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"", maxWidth: '1120px', margin: '0 auto' }}>")
    $content = $content.Replace("<form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(320px, 0.85fr)', gap: '1.5rem' }}>","<form className=""responsive-listing-form"" onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(320px, 0.85fr)', gap: '1.5rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem' }}>","<div className=""responsive-fields-2"" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1rem' }}>","<div className=""responsive-fields-3"" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>","<div className=""responsive-form-sidebar"" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>","<div className=""responsive-photo-grid"" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', alignItems: 'stretch', gap: '0.85rem', flexWrap: 'wrap' }}>","<div className=""responsive-form-actions"" style={{ display: 'flex', alignItems: 'stretch', gap: '0.85rem', flexWrap: 'wrap' }}>")
    return $content
}

Update-File "src\pages\seller\RelistListing.jsx" {
    param($content)
    $content = $content.Replace("<div style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"", padding: '1.5rem 0' }}>","<div className=""dashboard-page listing-form-page"" style={{ fontFamily: ""'Plus Jakarta Sans', sans-serif"", padding: '1.5rem 0' }}>")
    $content = $content.Replace("<form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: '1.5rem' }}>","<form className=""responsive-listing-form responsive-listing-form--relist"" onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: '1.5rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>","<div className=""responsive-fields-2"" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1rem' }}>","<div className=""responsive-fields-3"" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>","<div className=""responsive-form-sidebar"" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>")
    $content = $content.Replace("<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>","<div className=""responsive-photo-grid"" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>")
    $content = $content.Replace("<div style={{ display: 'flex', alignItems: 'stretch', gap: '0.85rem', flexWrap: 'wrap' }}>","<div className=""responsive-form-actions"" style={{ display: 'flex', alignItems: 'stretch', gap: '0.85rem', flexWrap: 'wrap' }}>")
    return $content
}
