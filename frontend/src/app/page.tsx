'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { fetchWithAuth, removeToken } from '@/lib/api';
import { LogOut, LineChart, MessageSquare, AlertTriangle, CloudRain, PackageSearch, Loader2 } from 'lucide-react';

export default function Dashboard() {
  const router = useRouter();
  const [store, setStore] = useState('1');
  const [item, setItem] = useState('1');
  const [city, setCity] = useState('New York');
  
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [polling, setPolling] = useState(false);

  // Poll for Celery Worker status
  useEffect(() => {
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

  const handleLogout = () => {
    removeToken();
    router.push('/login');
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
    setTaskStatus(prev => ({ ...prev, task_status: 'GENERATING_REPORT' }));
    
    try {
      const formData = new FormData();
      formData.append('forecast_summary', JSON.stringify(forecastResult.summary));
      formData.append('city', city);
      
      const res = await fetchWithAuth('/analyze', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Analysis failed');
      
      setReport(data.gemini_report);
      setTaskStatus(prev => ({ ...prev, task_status: 'COMPLETE' }));
    } catch (err: any) {
      setError(err.message);
      setTaskStatus(prev => ({ ...prev, task_status: 'ERROR' }));
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
              Forecast Parameters
            </h2>

            <div className="space-y-5 relative z-10">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Store ID</label>
                <select 
                  value={store} onChange={e => setStore(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-2.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white outline-none"
                >
                  {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>Store #{n}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Product ID</label>
                <select 
                  value={item} onChange={e => setItem(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-2.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all text-white outline-none"
                >
                  {[1, 2, 3, 4, 5, 10, 25, 50].map(n => <option key={n} value={n}>Item #{n}</option>)}
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
