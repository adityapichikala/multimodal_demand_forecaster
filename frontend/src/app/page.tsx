'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { fetchWithAuth, removeToken } from '@/lib/api';
import { LogOut, LineChart, MessageSquare, AlertTriangle, CloudRain, PackageSearch, Loader2, Upload } from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();
  // Selection State
  const [store, setStore] = useState('');
  const [item, setItem] = useState('');
  const [city, setCity] = useState('New York');
  
  // Available Meta State
  const [availableStores, setAvailableStores] = useState<number[]>([]);
  const [availableItems, setAvailableItems] = useState<{id: string | number, name: string}[]>([]);
  
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [polling, setPolling] = useState(false);
  
  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [clearExisting, setClearExisting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');

  // History state
  const [history, setHistory] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Poll for Celery Worker status
  useEffect(() => {
    fetchHistory();
    let interval: NodeJS.Timeout;
    
    const checkStatus = async () => {
      if (!taskStatus?.task_id) return;
      try {
        const res = await fetchWithAuth(`/task/${taskStatus.task_id}`);
        const data = await res.json();
        
        if (data.task_status === 'SUCCESS') {
          setTaskStatus(data);
          setPolling(false);
          // Auto-trigger Stage 2 (LLM Analysis)
          handleAnalyze(data.result);
        } else if (data.task_status === 'FAILURE') {
          setError(data.error || 'Forecasting failed');
          setPolling(false);
        } else {
          setTaskStatus(data);
        }
      } catch(e) {
        setPolling(false);
      }
    };

    if (polling) {
      interval = setInterval(checkStatus, 2000);
    }
    return () => clearInterval(interval);
  }, [polling, taskStatus]);

  const fetchMeta = async () => {
    try {
      const res = await fetchWithAuth('/dashboard-meta');
      if (res.ok) {
        const data = await res.json();
        if (!data) return;
        
        const stData = Array.isArray(data.stores) ? data.stores : [];
        const prData = Array.isArray(data.products) ? data.products : [];
        
        setAvailableStores(stData);
        setAvailableItems(prData);
        
        if (stData.length > 0 && !store) {
          const firstStore = stData[0];
          const stId = (firstStore && typeof firstStore === 'object') ? (firstStore.id || firstStore) : firstStore;
          if (stId !== null && stId !== undefined) setStore(stId.toString());
        }
        
        if (prData.length > 0 && !item) {
          const firstItem = prData[0];
          const itemId = (firstItem && typeof firstItem === 'object') ? (firstItem.id || firstItem) : firstItem;
          if (itemId !== null && itemId !== undefined) setItem(itemId.toString());
        }
      }
    } catch(e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchMeta();
  }, []);

  const handleLogout = () => {
    removeToken();
    router.push('/login');
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadMsg('');
    setError('');

    try {
      const formData = new FormData();
      formData.append('csv_file', file);
      formData.append('clear_all', String(clearExisting));
      
      const res = await fetchWithAuth('/upload-data', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');
      
      setUploadMsg(data.message || 'Upload successful! DB is seeded.');
      setFile(null);
      await fetchMeta(); // Refresh dropdowns
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleGenerateForecast = async () => {
    setError('');
    setReport(null);
    setTaskStatus({ task_status: 'PENDING' });
    
    try {
      const formData = new FormData();
      formData.append('store', store);
      formData.append('item', item);
      
      const res = await fetchWithAuth('/train-async', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');
      
      setTaskStatus({ task_id: data.task_id, task_status: 'PROCESSING' });
      setPolling(true);
    } catch (err: any) {
      setError(err.message);
      setTaskStatus(null);
    }
  };

  const handleAnalyze = async (forecastResult: any) => {
    setTaskStatus((prev: any) => ({ ...prev, task_status: 'GENERATING_REPORT' }));
    
    try {
      const formData = new FormData();
      formData.append('forecast_id', forecastResult.forecast_id.toString());
      formData.append('city', city);
      
      const res = await fetchWithAuth('/analyze', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Analysis failed');
      
      setReport(data.gemini_report);
      setTaskStatus((prev: any) => ({ ...prev, task_status: 'COMPLETE' }));
      fetchHistory(); // Refresh history list
    } catch (err: any) {
      setError(err.message);
      setTaskStatus((prev: any) => ({ ...prev, task_status: 'ERROR' }));
    }
  };

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await fetchWithAuth('/forecast-history');
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch (e) {
      console.error('Failed to fetch history:', e);
    } finally {
      setLoadingHistory(false);
    }
  };

  const loadPastForecast = async (id: number) => {
    setTaskStatus({ task_status: 'LOADING_PAST' });
    setReport(null);
    try {
      const res = await fetchWithAuth(`/forecast/${id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load forecast');
      
      setStore(String(data.store_id));
      setItem(String(data.product_id));
      setReport(data.gemini_report);
      setTaskStatus({ task_status: 'COMPLETE' });
    } catch (err: any) {
      setError(err.message);
      setTaskStatus(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      {/* Navbar */}
      <nav className="border-b border-gray-800 bg-gray-900 px-6 py-4 flex justify-between items-center sticky top-0 z-50 shadow-sm shadow-blue-900/10">
        <div className="flex items-center space-x-3">
          <LineChart className="text-blue-500 w-8 h-8" />
          <span className="text-xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">Nexus Demand Engine</span>
        </div>
        <button 
          onClick={handleLogout}
          className="flex items-center space-x-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        
        {/* Left Sidebar - Controls */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl" />
            
            <h2 className="text-lg font-semibold text-white mb-6 flex items-center">
              <PackageSearch className="w-5 h-5 mr-2 text-blue-400" />
              1. Feed Intelligence Data
            </h2>

            <form onSubmit={handleUpload} className="space-y-4 relative z-10 mb-8 pb-6 border-b border-gray-800">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Upload Historical Sales (CSV)</label>
                <div className="flex items-center space-x-3">
                  <input 
                    type="file" 
                    accept=".csv,.xlsx,.xls"
                    onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
                    className="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-900/30 file:text-blue-400 hover:file:bg-blue-900/50 cursor-pointer"
                  />
                  <button 
                    type="submit"
                    disabled={!file || uploading}
                    className="bg-blue-600 hover:bg-blue-500 text-white p-2.5 rounded-lg disabled:opacity-50 transition-colors"
                  >
                    {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                  </button>
                </div>
                <div className="flex items-center space-x-2 mt-2">
                  <input 
                    type="checkbox" 
                    id="clear_existing"
                    checked={clearExisting}
                    onChange={(e) => setClearExisting(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-700 bg-gray-950 text-blue-500 focus:ring-blue-500"
                  />
                  <label htmlFor="clear_existing" className="text-sm text-gray-400 cursor-pointer">
                    Clear existing data history
                  </label>
                </div>
                {uploadMsg && <p className="text-green-400 text-sm mt-3 flex items-center">{uploadMsg}</p>}
              </div>
            </form>

            {/* History Section */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold flex items-center space-x-2">
                  <MessageSquare className="text-blue-400 w-5 h-5" />
                  <span>Recent Analysis</span>
                </h2>
                <button 
                  onClick={fetchHistory} 
                  disabled={loadingHistory}
                  className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
                >
                  {loadingHistory ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
              
              <div className="space-y-3 max-h-[350px] overflow-y-auto pr-2 custom-scrollbar">
                {loadingHistory && history.length === 0 ? (
                    <div className="flex justify-center py-4"><Loader2 className="w-6 h-6 animate-spin text-gray-500" /></div>
                ) : history.length === 0 ? (
                    <p className="text-sm text-gray-500 text-center py-4 italic">No past forecasts found.</p>
                ) : (
                  history.map((h) => (
                    <button 
                      key={h.id}
                      onClick={() => loadPastForecast(h.id)}
                      className="w-full text-left p-3 rounded-xl bg-gray-950/50 border border-gray-800 hover:border-blue-500/50 hover:bg-blue-900/10 transition-all group"
                    >
                      <div className="flex justify-between items-start mb-1">
                        <span className="text-xs font-semibold text-blue-400 group-hover:text-blue-300 transition-colors uppercase tracking-wider">{h.product_name}</span>
                        <span className="text-[10px] text-gray-600 font-mono">{new Date(h.created_at).toLocaleDateString()}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="bg-gray-800 text-gray-400 text-[9px] px-1.5 py-0.5 rounded uppercase font-bold">Store {h.store_id}</span>
                        <span className={`text-[9px] font-medium ${h.has_report ? 'text-green-500/80' : 'text-yellow-500/80'}`}>
                          {h.has_report ? '• Report Ready' : '• Incomplete'}
                        </span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            <h2 className="text-lg font-semibold text-white mb-6 flex items-center">
              <PackageSearch className="w-5 h-5 mr-2 text-indigo-400" />
              2. Forecast Parameters
            </h2>

            <div className="space-y-5 relative z-10">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Store ID</label>
                <select 
                  value={store} onChange={e => setStore(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-2.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white outline-none"
                >
                  {availableStores.length === 0 ? (
                    <option value="" disabled>No data uploaded</option>
                  ) : (
                    availableStores.map((n: any) => {
                      const val = (n && typeof n === 'object') ? (n.id || n) : n;
                      return <option key={String(val)} value={String(val)}>{String(val)}</option>;
                    })
                  )}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Product</label>
                <select 
                  value={item} onChange={e => setItem(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-2.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white outline-none"
                >
                  {availableItems.length === 0 ? (
                    <option value="" disabled>No data uploaded</option>
                  ) : (
                    availableItems.map((p: any) => {
                      const id = (p && typeof p === 'object') ? p.id : p;
                      const name = (p && typeof p === 'object') ? p.name : String(id);
                      const displayId = String(id);
                      const displayName = String(name);
                      return (
                        <option key={displayId} value={displayId}>
                          {displayName}
                        </option>
                      );
                    })
                  )}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2 flex items-center">
                  Target Market Segment (City)
                </label>
                <input 
                  type="text" value={city} onChange={e => setCity(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-2.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white outline-none"
                />
              </div>

              <button 
                onClick={handleGenerateForecast}
                disabled={polling || taskStatus?.task_status === 'GENERATING_REPORT'}
                className="w-full mt-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium py-3 px-4 rounded-xl shadow-lg shadow-blue-500/25 transition-all active:scale-[0.98] disabled:opacity-50 flex justify-center items-center"
              >
                {polling || taskStatus?.task_status === 'GENERATING_REPORT' ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  'Generate Intelligence Report'
                )}
              </button>
            </div>
          </div>
          
          {/* Status Indicator */}
          {taskStatus && (
            <div className={`rounded-xl p-4 border flex items-center space-x-3 transition-colors ${
              taskStatus.task_status === 'COMPLETE' ? 'bg-green-500/10 border-green-500/30 text-green-400' :
              taskStatus.task_status === 'ERROR' ? 'bg-red-500/10 border-red-500/30 text-red-400' :
              'bg-blue-500/10 border-blue-500/30 text-blue-400'
            }`}>
              {taskStatus.task_status === 'COMPLETE' ? <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"/> : 
               taskStatus.task_status === 'ERROR' ? <AlertTriangle className="w-4 h-4"/> :
               <Loader2 className="w-4 h-4 animate-spin"/>}
              <span className="text-sm font-medium tracking-wide">
                SYSTEM STATUS: {taskStatus.task_status}
              </span>
            </div>
          )}

          {error && (
            <div className="bg-red-950 border border-red-900 text-red-400 p-4 rounded-xl text-sm break-words shadow-lg">
              <span className="font-bold flex items-center"><AlertTriangle className="w-4 h-4 mr-2"/> Error</span>
              <p className="mt-1 opacity-90">{error}</p>
            </div>
          )}
        </div>

        {/* Right Sidebar - Report Output */}
        <div className="lg:col-span-8">
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl min-h-[600px] h-full flex flex-col relative overflow-hidden">
            <div className="absolute top-0 left-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />
            
            <h2 className="text-xl font-semibold text-white mb-6 flex items-center border-b border-gray-800 pb-4 relative z-10">
              <MessageSquare className="w-5 h-5 mr-3 text-indigo-400" />
              Multi-Agent Verification Pipeline Output
            </h2>
            
            <div className="flex-1 overflow-auto custom-scrollbar relative z-10">
              {!report ? (
                 <div className="h-full flex flex-col items-center justify-center text-gray-500 space-y-4">
                  <div className="w-16 h-16 rounded-2xl bg-gray-800 flex items-center justify-center border border-gray-700">
                    <CloudRain className="w-8 h-8 opacity-50" />
                  </div>
                  <p>Awaiting parameters to synthesize report.</p>
                 </div>
              ) : (
                <div className="prose prose-invert prose-blue max-w-none text-gray-300">
                  {/* Minimalistic markdown rendering (could be replaced with react-markdown) */}
                  {report.split('\n').map((line, i) => {
                    if (line.startsWith('# ')) return <h1 key={i} className="text-2xl font-bold text-white mt-8 mb-4 border-b border-gray-800 pb-2">{line.replace('# ', '')}</h1>;
                    if (line.startsWith('## ')) return <h2 key={i} className="text-xl font-semibold text-white mt-6 mb-3">{line.replace('## ', '')}</h2>;
                    if (line.startsWith('### ')) return <h3 key={i} className="text-lg font-medium text-white mt-4 mb-2">{line.replace('### ', '')}</h3>;
                    if (line.startsWith('- ') || line.startsWith('* ')) return <li key={i} className="ml-4 mt-1 opacity-90">{line.substring(2)}</li>;
                    if (line.trim() === '') return <br key={i}/>;
                    if (line.includes('**')) { // simple bold parser
                      const parts = line.split('**');
                      return <p key={i} className="leading-relaxed opacity-90">{parts.map((part, j) => j % 2 !== 0 ? <strong key={j} className="text-white font-semibold">{part}</strong> : part)}</p>;
                    }
                    return <p key={i} className="leading-relaxed opacity-90">{line}</p>;
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
