const { useState, useEffect, useRef } = React;

// API Client
const API_BASE = window.location.origin;

const api = {
    async getMetrics() {
        try {
            const res = await fetch(`${API_BASE}/metrics`);
            return res.ok ? await res.json() : null;
        } catch (e) {
            return null;
        }
    },
    async getPrometheusMetrics() {
        try {
            const res = await fetch(`${API_BASE}/metrics/prometheus`);
            return res.ok ? await res.text() : null;
        } catch (e) {
            return null;
        }
    },
    async getABTestStatus() {
        try {
            const res = await fetch(`${API_BASE}/ab-test/status`);
            return res.ok ? await res.json() : null;
        } catch (e) {
            return null;
        }
    },
    async getHealth() {
        try {
            const res = await fetch(`${API_BASE}/health`);
            return res.ok ? await res.json() : null;
        } catch (e) {
            return null;
        }
    },
    async getTemplates() {
        try {
            const res = await fetch(`${API_BASE}/templates`);
            return res.ok ? await res.json() : null;
        } catch (e) {
            return null;
        }
    }
};

// Components
const Card = ({ title, value, icon, color = "blue", subtitle = null }) => {
    const colors = {
        blue: "bg-blue-500",
        green: "bg-green-500",
        yellow: "bg-yellow-500",
        red: "bg-red-500",
        purple: "bg-purple-500",
    };

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-gray-500 text-sm uppercase font-semibold">{title}</p>
                    <p className="text-3xl font-bold text-gray-800 mt-1">{value}</p>
                    {subtitle && <p className="text-gray-400 text-sm mt-1">{subtitle}</p>}
                </div>
                <div className={`${colors[color]} rounded-full p-3 text-white`}>
                    <i className={`fas ${icon} text-xl`}></i>
                </div>
            </div>
        </div>
    );
};

const MetricChart = ({ data, title, color = "blue" }) => {
    const canvasRef = useRef(null);
    const chartRef = useRef(null);

    useEffect(() => {
        if (canvasRef.current && data) {
            if (chartRef.current) {
                chartRef.current.destroy();
            }

            const ctx = canvasRef.current.getContext('2d');
            chartRef.current = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [{
                        label: title,
                        data: data.values,
                        borderColor: color === 'blue' ? '#3b82f6' : color === 'green' ? '#10b981' : '#f59e0b',
                        backgroundColor: color === 'blue' ? 'rgba(59, 130, 246, 0.1)' : color === 'green' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                        fill: true,
                        tension: 0.4,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });
        }

        return () => {
            if (chartRef.current) {
                chartRef.current.destroy();
            }
        };
    }, [data, title, color]);

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">{title}</h3>
            <div style={{ height: '250px' }}>
                <canvas ref={canvasRef}></canvas>
            </div>
        </div>
    );
};

const ABTestPanel = ({ status }) => {
    if (!status) return <div className="text-gray-500">Loading A/B test status...</div>;

    const isEnabled = status.enabled;
    const metrics = status.metrics || {};

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-800">A/B Testing</h3>
                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${isEnabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                    {isEnabled ? 'Enabled' : 'Disabled'}
                </span>
            </div>

            {isEnabled && (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-blue-50 rounded-lg p-4">
                            <p className="text-sm text-gray-600">Control</p>
                            <p className="text-2xl font-bold text-blue-600">{metrics.control?.requests || 0}</p>
                            <p className="text-xs text-gray-500">requests</p>
                        </div>
                        <div className="bg-purple-50 rounded-lg p-4">
                            <p className="text-sm text-gray-600">Experimental</p>
                            <p className="text-2xl font-bold text-purple-600">{metrics.experimental?.requests || 0}</p>
                            <p className="text-xs text-gray-500">requests</p>
                        </div>
                    </div>

                    <div className="border-t pt-4">
                        <p className="text-sm text-gray-600 mb-2">Configuration</p>
                        <div className="space-y-1 text-sm">
                            <div className="flex justify-between">
                                <span className="text-gray-500">Traffic Split:</span>
                                <span className="font-medium">{(status.config?.traffic_split * 100).toFixed(0)}% to experimental</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-500">Sticky Sessions:</span>
                                <span className="font-medium">{status.config?.sticky_sessions ? 'Yes' : 'No'}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-500">Experimental Upstream:</span>
                                <span className="font-medium truncate max-w-xs">{status.config?.experimental_upstream || 'N/A'}</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const CachePanel = ({ metrics }) => {
    const cacheHitRate = metrics?.cache_hit_rate || 0;
    const cacheHits = metrics?.cache_hits || 0;
    const cacheMisses = metrics?.cache_misses || 0;

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Cache Performance</h3>
            
            <div className="flex items-center justify-center mb-6">
                <div className="relative w-32 h-32">
                    <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                        <path className="text-gray-200" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                        <path className="text-green-500" strokeDasharray={`${cacheHitRate * 100}, 100`} d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                        <span className="text-2xl font-bold text-gray-800">{(cacheHitRate * 100).toFixed(1)}%</span>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="text-center">
                    <p className="text-2xl font-bold text-green-600">{cacheHits}</p>
                    <p className="text-sm text-gray-500">Hits</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-gray-600">{cacheMisses}</p>
                    <p className="text-sm text-gray-500">Misses</p>
                </div>
            </div>
        </div>
    );
};

const TemplatesPanel = ({ templates }) => {
    if (!templates) return <div className="text-gray-500">Loading templates...</div>;

    const templateList = templates.templates || [];

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-800">Prompt Templates</h3>
                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-semibold">
                    {templateList.length} templates
                </span>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto">
                {templateList.map((template, idx) => (
                    <div key={idx} className="border rounded-lg p-3 hover:bg-gray-50">
                        <div className="flex items-center justify-between">
                            <span className="font-medium text-gray-800">{template.name}</span>
                            <span className="text-xs text-gray-500">{template.variable_count} vars</span>
                        </div>
                        <p className="text-sm text-gray-600 mt-1 truncate">{template.description}</p>
                    </div>
                ))}
            </div>
        </div>
    );
};

// Main App
const App = () => {
    const [metrics, setMetrics] = useState(null);
    const [abStatus, setABStatus] = useState(null);
    const [templates, setTemplates] = useState(null);
    const [health, setHealth] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('overview');

    // Historical data for charts
    const [requestHistory, setRequestHistory] = useState({ labels: [], values: [] });
    const [latencyHistory, setLatencyHistory] = useState({ labels: [], values: [] });

    useEffect(() => {
        const fetchData = async () => {
            const [metricsData, abData, templatesData, healthData] = await Promise.all([
                api.getMetrics(),
                api.getABTestStatus(),
                api.getTemplates(),
                api.getHealth()
            ]);

            setMetrics(metricsData);
            setABStatus(abData);
            setTemplates(templatesData);
            setHealth(healthData);
            setLoading(false);

            // Update chart data
            const now = new Date().toLocaleTimeString();
            setRequestHistory(prev => ({
                labels: [...prev.labels.slice(-19), now],
                values: [...prev.values.slice(-19), metricsData?.requests_total || 0]
            }));
            setLatencyHistory(prev => ({
                labels: [...prev.labels.slice(-19), now],
                values: [...prev.values.slice(-19), metricsData?.avg_latency_ms || 0]
            }));
        };

        fetchData();
        const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds

        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <i className="fas fa-circle-notch fa-spin text-4xl text-blue-500 mb-4"></i>
                    <p className="text-gray-600">Loading dashboard...</p>
                </div>
            </div>
        );
    }

    const summary = metrics || {};

    return (
        <div className="min-h-screen bg-gray-100">
            {/* Header */}
            <header className="bg-white shadow-sm">
                <div className="max-w-7xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-4">
                            <div className="bg-blue-600 rounded-lg p-2">
                                <i className="fas fa-server text-white text-xl"></i>
                            </div>
                            <div>
                                <h1 className="text-2xl font-bold text-gray-800">LLM Proxy Dashboard</h1>
                                <p className="text-sm text-gray-500">Version {health?.version || '0.1.0'}</p>
                            </div>
                        </div>
                        <div className="flex items-center space-x-4">
                            <div className={`px-4 py-2 rounded-full text-sm font-semibold ${health?.status === 'healthy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                <i className={`fas ${health?.status === 'healthy' ? 'fa-check-circle' : 'fa-exclamation-circle'} mr-2`}></i>
                                {health?.status === 'healthy' ? 'Healthy' : 'Unhealthy'}
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            {/* Navigation */}
            <nav className="bg-white border-t">
                <div className="max-w-7xl mx-auto px-4">
                    <div className="flex space-x-8">
                        {['overview', 'metrics', 'templates', 'logs'].map((tab) => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`py-4 px-2 border-b-2 font-medium text-sm capitalize ${
                                    activeTab === tab
                                        ? 'border-blue-500 text-blue-600'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                            >
                                {tab}
                            </button>
                        ))}
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 py-8">
                {activeTab === 'overview' && (
                    <div className="space-y-6">
                        {/* Key Metrics */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                            <Card
                                title="Total Requests"
                                value={summary.requests_total?.toLocaleString() || '0'}
                                icon="fa-chart-line"
                                color="blue"
                            />
                            <Card
                                title="Cache Hit Rate"
                                value={`${((summary.cache_hit_rate || 0) * 100).toFixed(1)}%`}
                                icon="fa-bolt"
                                color="yellow"
                                subtitle={`${summary.cache_hits || 0} hits, ${summary.cache_misses || 0} misses`}
                            />
                            <Card
                                title="Avg Latency"
                                value={`${(summary.avg_latency_ms || 0).toFixed(0)}ms`}
                                icon="fa-clock"
                                color="green"
                            />
                            <Card
                                title="Errors"
                                value={summary.errors_total?.toLocaleString() || '0'}
                                icon="fa-exclamation-triangle"
                                color={summary.errors_total > 0 ? "red" : "green"}
                            />
                        </div>

                        {/* Secondary Metrics */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                            <Card
                                title="Upstream Tokens"
                                value={(summary.tokens_upstream || 0).toLocaleString()}
                                icon="fa-upload"
                                color="purple"
                            />
                            <Card
                                title="Downstream Tokens"
                                value={(summary.tokens_downstream || 0).toLocaleString()}
                                icon="fa-download"
                                color="purple"
                            />
                            <Card
                                title="Tokens Saved"
                                value={(summary.tokens_saved || 0).toLocaleString()}
                                icon="fa-compress-alt"
                                color="green"
                            />
                            <Card
                                title="Est. Cost Savings"
                                value={`$${((summary.tokens_saved || 0) * 0.01 / 1000).toFixed(2)}`}
                                icon="fa-dollar-sign"
                                color="green"
                            />
                        </div>

                        {/* Charts Row */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <MetricChart
                                data={requestHistory}
                                title="Request Rate"
                                color="blue"
                            />
                            <MetricChart
                                data={latencyHistory}
                                title="Latency (ms)"
                                color="green"
                            />
                        </div>

                        {/* Bottom Row */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            <ABTestPanel status={abStatus} />
                            <CachePanel metrics={summary} />
                            <TemplatesPanel templates={templates} />
                        </div>
                    </div>
                )}

                {activeTab === 'metrics' && (
                    <div className="space-y-6">
                        <div className="bg-white rounded-lg shadow-md p-6">
                            <h2 className="text-xl font-semibold text-gray-800 mb-4">Detailed Metrics</h2>
                            <pre className="bg-gray-100 rounded-lg p-4 overflow-x-auto text-sm">
                                {JSON.stringify(metrics, null, 2)}
                            </pre>
                        </div>
                    </div>
                )}

                {activeTab === 'templates' && (
                    <div className="space-y-6">
                        <TemplatesPanel templates={templates} />
                    </div>
                )}

                {activeTab === 'logs' && (
                    <div className="bg-white rounded-lg shadow-md p-6">
                        <h2 className="text-xl font-semibold text-gray-800 mb-4">Live Logs</h2>
                        <div className="bg-gray-900 rounded-lg p-4 font-mono text-sm text-green-400 h-96 overflow-y-auto">
                            <p>[2025-04-03 21:30:00] INFO: LLM Proxy Dashboard started</p>
                            <p>[2025-04-03 21:30:01] INFO: Connected to upstream API</p>
                            <p>[2025-04-03 21:30:05] INFO: Cache initialized (memory backend)</p>
                            <p>[2025-04-03 21:30:05] INFO: Metrics endpoint ready</p>
                            <p className="animate-pulse">_</p>
                        </div>
                    </div>
                )}
            </main>

            {/* Footer */}
            <footer className="bg-white border-t mt-12">
                <div className="max-w-7xl mx-auto px-4 py-6">
                    <div className="flex items-center justify-between text-sm text-gray-500">
                        <p>LLM Proxy Dashboard v0.1.0</p>
                        <div className="flex space-x-4">
                            <a href="/health" className="hover:text-blue-600">Health Check</a>
                            <a href="/metrics" className="hover:text-blue-600">Metrics API</a>
                            <a href="/metrics/prometheus" className="hover:text-blue-600">Prometheus</a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
