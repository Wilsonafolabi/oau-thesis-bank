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

const Screen24IdeaExtension = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="How to Differentiate Your Research">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8 flex items-center cursor-pointer text-slate-500 hover:text-slate-800" onClick={() => navigate('idea-similarity')}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Analysis
        </div>
        
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Differentiation Strategies</h2>
        <p className="text-slate-600 mb-8">Based on the limitations and future work sections of similar OAU theses, here are data-driven ways to make your idea novel.</p>

        <div className="space-y-6">
          <Card className="p-6 border-l-4 border-l-[#00502F]">
            <div className="flex items-start space-x-4">
              <div className="p-2 bg-emerald-50 text-[#00502F] rounded-lg"><Database className="w-6 h-6"/></div>
              <div>
                <h3 className="text-lg font-semibold text-slate-900">Change the Dataset Context</h3>
                <p className="text-slate-600 mt-2 text-sm leading-relaxed">Previous works relied heavily on standard laboratory-prepared slide images (e.g., NIH datasets). <strong>Novel approach:</strong> Collect and use a dataset of field-prepared thick smears from rural clinics in Osun State to test real-world robustness.</p>
              </div>
            </div>
          </Card>

          <Card className="p-6 border-l-4 border-l-[#D4AF37]">
            <div className="flex items-start space-x-4">
              <div className="p-2 bg-yellow-50 text-yellow-700 rounded-lg"><Cpu className="w-6 h-6"/></div>
              <div>
                <h3 className="text-lg font-semibold text-slate-900">Address Computational Constraints</h3>
                <p className="text-slate-600 mt-2 text-sm leading-relaxed">Previous researchers noted their models were too heavy to run offline on budget smartphones. <strong>Novel approach:</strong> Focus your research on model quantization and edge-computing techniques (like MobileNetV3) specifically for low-end Android devices common in Nigeria.</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen24IdeaExtension;
