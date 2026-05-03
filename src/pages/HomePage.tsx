import React, { useRef, useEffect } from 'react';

/**
 * Mock-Komponenten für das Layout.
 */
const Header: React.FC = () => (
  <header className="bg-blue-600 text-white p-4 shadow-md z-10 relative">
    <div className="container mx-auto flex justify-between items-center">
      <h1 className="text-xl font-bold">App Dashboard</h1>
      <nav>
        <ul className="flex space-x-4">
          <li><a href="/" className="hover:underline">Home</a></li>
          <li><a href="/settings" className="hover:underline">Einstellungen</a></li>
        </ul>
      </nav>
    </div>
  </header>
);

const Footer: React.FC = () => (
  <footer className="bg-gray-800 text-gray-300 p-6 mt-auto z-10 relative">
    <div className="container mx-auto text-center">
      <p>&copy; {new Date().getFullYear()} Application Suite. Alle Rechte vorbehalten.</p>
    </div>
  </footer>
);

const FeatureCard: React.FC<{ title: string; description: string; icon: string }> = ({ title, description, icon }) => (
  <div className="bg-white/80 backdrop-blur-md p-6 rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
    <div className="text-3xl mb-4">{icon}</div>
    <h3 className="text-lg font-semibold mb-2">{title}</h3>
    <p className="text-gray-600 text-sm">{description}</p>
  </div>
);

/**
 * Antigravity Canvas Komponente
 * Implementiert eine generative Loop-Logik mit direkter DOM-Manipulation via Refs.
 */
const AntigravityCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];

    class Particle {
      x: number = 0;
      y: number = 0;
      size: number = 0;
      speedY: number = 0;
      color: string = '';

      constructor() {
        this.reset();
      }

      reset() {
        this.x = Math.random() * (canvas?.width || 0);
        this.y = (canvas?.height || 0) + Math.random() * 100;
        this.size = Math.random() * 3 + 1;
        this.speedY = Math.random() * -1.5 - 0.5;
        this.color = `rgba(59, 130, 246, ${Math.random() * 0.5 + 0.1})`;
      }

      update() {
        this.y += this.speedY;
        if (this.y + this.size < 0) {
          this.reset();
        }
      }

      draw() {
        if (!ctx) return;
        ctx.fillStyle = this.color;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const init = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      particles = [];
      for (let i = 0; i < 100; i++) {
        particles.push(new Particle());
      }
    };

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((particle) => {
        particle.update();
        particle.draw();
      });
      animationFrameId = requestAnimationFrame(animate);
    };

    const handleResize = () => {
      init();
    };

    window.addEventListener('resize', handleResize);
    init();
    animate();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed top-0 left-0 w-full h-full pointer-events-none -z-0"
    />
  );
};

const HomePage: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 relative overflow-hidden">
      <AntigravityCanvas />
      
      <Header />

      <main className="flex-grow container mx-auto px-4 py-12 z-10 relative">
        <header className="mb-12 text-center">
          <h2 className="text-4xl font-extrabold text-gray-900 mb-4">
            Zentrale Verwaltung
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Willkommen zurück. Hier finden Sie alle integrierten Features und Module auf einen Blick.
          </p>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <FeatureCard 
            title="Statistiken" 
            description="Echtzeit-Analyse Ihrer Datenströme und Performance-Metriken." 
            icon="📊" 
          />
          <FeatureCard 
            title="Benutzerverwaltung" 
            description="Verwalten Sie Rollen, Rechte und Profile Ihrer Teammitglieder." 
            icon="👥" 
          />
          <FeatureCard 
            title="Ressourcen-Planer" 
            description="Optimieren Sie die Zuweisung Ihrer vorhandenen Kapazitäten." 
            icon="📅" 
          />
          <FeatureCard 
            title="Sicherheit" 
            description="Überwachen Sie Zugriffsprotokolle und Verschlüsselungsparameter." 
            icon="🛡️" 
          />
          <FeatureCard 
            title="Cloud-Speicher" 
            description="Direkter Zugriff auf Ihre Dokumente und Medien-Assets." 
            icon="☁️" 
          />
          <FeatureCard 
            title="API-Konsole" 
            description="Testen und konfigurieren Sie Ihre externen Schnittstellen." 
            icon="🔌" 
          />
        </section>

        <section className="mt-16 bg-blue-50/70 backdrop-blur-sm p-8 rounded-2xl border border-blue-100">
          <div className="flex flex-col md:flex-row items-center justify-between">
            <div>
              <h3 className="text-2xl font-bold text-blue-900 mb-2">System-Status: Optimal</h3>
              <p className="text-blue-700">Alle Dienste laufen stabil. Letzte Synchronisierung: Gerade eben.</p>
            </div>
            <button className="mt-4 md:mt-0 bg-blue-600 text-white px-6 py-2 rounded-full font-medium hover:bg-blue-700 transition-colors shadow-lg">
              System-Check starten
            </button>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default HomePage;