import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen13ResearchLineage = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Research Lineage">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-2xl font-bold text-slate-900">Lineage Explorer</h2>
          <p className="text-slate-500 mt-2">Visualizing the impact and evolution of this research idea.</p>
        </div>

        <div className="relative flex flex-col items-center py-10">
          {/* Vertical connecting line */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-slate-200 left-1/2 transform -translate-x-1/2 -z-10"></div>

          {/* Node 1: Root */}
          <motion.div initial={{opacity:0, y:20}} animate={{opacity:1, y:0}} className="mb-12 relative w-full max-w-lg">
            <Card className="p-5 border-2 border-[#D4AF37] relative bg-yellow-50/30">
              <div className="absolute -left-3 top-1/2 transform -translate-y-1/2 w-6 h-6 rounded-full bg-[#D4AF37] border-4 border-white flex items-center justify-center"><ArrowRight className="w-3 h-3 text-white"/></div>
              <Badge variant="gold" className="mb-2">Foundation Concept (2019)</Badge>
              <h3 className="font-semibold text-slate-900 cursor-pointer hover:text-[#00502F]" onClick={() => navigate('thesis-detail')}>Statistical Analysis of Rainfall on Maize Yields</h3>
              <p className="text-xs text-slate-500 mt-1">O. B. Johnson • Dept of Agriculture</p>
            </Card>
          </motion.div>

          {/* Node 2: Current */}
          <motion.div initial={{opacity:0, y:20}} animate={{opacity:1, y:0}} transition={{delay:0.2}} className="mb-12 relative w-full max-w-lg md:translate-x-12">
            <Card className="p-5 border-2 border-[#00502F] shadow-md relative bg-white">
              <div className="absolute -left-3 top-1/2 transform -translate-y-1/2 w-6 h-6 rounded-full bg-[#00502F] border-4 border-white"></div>
              <Badge variant="green" className="mb-2">Current Thesis (2023)</Badge>
              <h3 className="font-semibold text-slate-900">Machine Learning for Crop Yield Prediction in Nigeria</h3>
              <p className="text-xs text-slate-500 mt-1">Adekunle Ojo • Dept of Agricultural Engineering</p>
            </Card>
          </motion.div>

          {/* Node 3: Future / Extension */}
          <motion.div initial={{opacity:0, y:20}} animate={{opacity:1, y:0}} transition={{delay:0.4}} className="mb-12 relative w-full max-w-lg md:-translate-x-12">
            <Card className="p-5 border border-slate-300 relative bg-slate-50 opacity-80 hover:opacity-100 transition-opacity cursor-pointer" onClick={() => navigate('thesis-detail')}>
              <div className="absolute right-0 top-1/2 transform translate-x-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-slate-300 border-4 border-white"></div>
              <Badge variant="gray" className="mb-2">Derived Work (Ongoing)</Badge>
              <h3 className="font-semibold text-slate-700">Deep Learning Integration for Multi-Crop Systems</h3>
              <p className="text-xs text-slate-500 mt-1">T. A. Salami • Dept of Computer Science</p>
            </Card>
          </motion.div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen13ResearchLineage;
